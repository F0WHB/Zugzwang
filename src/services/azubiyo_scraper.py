"""
ZUGZWANG - Azubiyo.de Scraper
High-performance scraper for azubiyo.de apprenticeships and dual studies.
Direct slug routing, fast detail extraction, direct online bewerbung resolution,
company profile fallback, and Google Maps website crawler integration.
"""

import asyncio
import json
import re
import urllib.request
from typing import AsyncGenerator, Optional
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup

from .browser import BrowserSession, BrowserError
from .website_crawler import WebsiteEmailCrawler
from .email_extractor import (
    extract_contact_person_from_html,
    extract_contact_person_from_text,
    extract_emails_from_html,
    deduplicate_emails,
    normalize_phone,
    normalize_website,
)
from ..core.security import LicenseManager
from ..core.events import event_bus
from ..core.logger import get_logger
from ..core.models import LeadRecord, SearchConfig, SourceType

logger = get_logger(__name__)

# Excluded domains when resolving external employer websites
_EXCLUDED_EXTERNAL_DOMAINS = {
    "azubiyo.de",
    "funkeworks.de",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "whatsapp.com",
    "consentmanager.net",
    "google.com",
    "googletagmanager.com",
    "doubleclick.net",
    "schema.org",
    "w3.org",
    "apple.com",
    "play.google.com",
    "t.co",
    "bit.ly",
    "tinyurl.com",
    "linktr.ee",
    "vonq.io",
    "gohiring.com",
    "fontawesome.com",
    "bing.com",
    "doubleclick.net",
    "visualwebsiteoptimizer.com",
    "podigee.io",
    "spotify.com",
    "soundcloud.com",
}


def slugify_city(city: str) -> str:
    """Convert a German city name into an Azubiyo-compatible URL slug."""
    c = re.sub(
        r"\s+(?:am\s+Main|a\.M\.|a\.d\..*|an\s+der\s+.*|im\s+.*|i\.d\..*)$",
        "",
        city.strip(),
        flags=re.IGNORECASE,
    ).strip()
    s = c.lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def is_valid_company_url(href: str) -> bool:
    """Check if a URL points to an external business/company domain rather than tracking/socials."""
    if not href or not href.startswith("http"):
        return False
    try:
        parsed = urlparse(href)
        domain = parsed.netloc.lower().split(":")[0]
        if not domain:
            return False
        for ex in _EXCLUDED_EXTERNAL_DOMAINS:
            if domain == ex or domain.endswith("." + ex):
                return False
        return True
    except Exception:
        return False


def _fast_fetch_html(url: str, timeout: float = 4.0) -> str | None:
    """Lightweight HTTP fetch to parse listing, detail, and bewerben pages without browser overhead."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def _fast_fetch_html_and_url(url: str, timeout: float = 4.0) -> tuple[str | None, str]:
    """Fetch HTML and return both the content and the final URL after redirects."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore"), resp.geturl()
    except Exception:
        return None, url


def _check_url_exists(url: str, timeout: float = 2.5) -> bool:
    """Quick HTTP check to test if a slugified route returns HTTP 200."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode() == 200
    except Exception:
        return False


class AzubiyoScraper:
    def __init__(self, session: BrowserSession, config: SearchConfig, job_id: str):
        self.session = session
        self.config = config
        self.job_id = job_id
        self._cancelled = False
        self._paused = False
        self._total_errors = 0
        self.crawler = WebsiteEmailCrawler(session, max_pages=5) if config.scrape_emails else None
        self._base_path: str = "https://www.azubiyo.de/stellenmarkt"

    def cancel(self):
        self._cancelled = True

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    async def _dismiss_cookies(self, page) -> None:
        """Dismiss ConsentManager cookie banner if present."""
        try:
            cookie_el = page.locator(
                '#cmpwelcomebtnyes, #cmpbntyestxt, button:has-text("Alle akzeptieren"), span:has-text("Alle akzeptieren")'
            ).first
            if await cookie_el.is_visible(timeout=1500):
                await cookie_el.click()
        except Exception:
            pass

        try:
            await page.evaluate("""() => {
                const btn = document.getElementById('cmpwelcomebtnyes') || document.getElementById('cmpbntyestxt');
                if (btn) btn.click();
                const box = document.getElementById('cmpbox');
                if (box) box.remove();
                const bd = document.querySelector('.cmpbox-backdrop, #cmpboxmodal');
                if (bd) bd.remove();
            }""")
        except Exception:
            pass

    def _init_base_path(self) -> None:
        """Determine base search path ONCE at startup to avoid route jitter."""
        city = (self.config.city or self.config.region or "").strip()
        city_slug = slugify_city(city) if city else ""
        if city_slug and _check_url_exists(f"https://www.azubiyo.de/ausbildung/{city_slug}/"):
            self._base_path = f"https://www.azubiyo.de/ausbildung/{city_slug}"
        else:
            self._base_path = "https://www.azubiyo.de/stellenmarkt"

    def _build_search_url(self, page_num: int = 1) -> str:
        """Build search URL for given page number."""
        job = (self.config.job_title or "").strip()
        city = (self.config.city or self.config.region or "").strip()
        radius = str(getattr(self.config, "radius", 25) or 25)

        query_params = []
        if job:
            query_params.append(f"subject={quote(job)}")
        if city:
            query_params.append(f"location={quote(city)}")
        if radius:
            query_params.append(f"radius={radius}")
        query_str = "&".join(query_params)

        base = self._base_path
        if page_num > 1:
            return f"{base}/{page_num}/?{query_str}" if query_str else f"{base}/{page_num}/"
        return f"{base}/?{query_str}" if query_str else f"{base}/"

    async def scrape(self) -> AsyncGenerator[LeadRecord, None]:
        location_val = (self.config.city or self.config.region or "").strip()
        job_val = (self.config.job_title or "").strip()

        logger.info(f"[{self.job_id}] Starting Azubiyo scrape: '{job_val}' in '{location_val}'")
        event_bus.emit(
            event_bus.JOB_LOG,
            job_id=self.job_id,
            message=f"Starting Azubiyo search for '{job_val or 'All Roles'}' in '{location_val or 'Germany'}'",
            level="INFO",
        )

        self._init_base_path()
        logger.info(f"[{self.job_id}] Azubiyo base path established: {self._base_path}")

        page = await self.session.new_page()
        try:
            page_num = 1
            yielded_count = 0
            processed_urls: set[str] = set()
            emitted_keys: set[str] = set()

            # Concurrency limit for background enrichment (same as Google Maps scraper)
            enrich_semaphore = asyncio.Semaphore(5)

            while not self._cancelled and yielded_count < self.config.max_results:
                while self._paused and not self._cancelled:
                    await asyncio.sleep(0.1)
                if self._cancelled:
                    break

                target_url = self._build_search_url(page_num=page_num)
                logger.info(f"[{self.job_id}] Navigating to Azubiyo page {page_num}: {target_url}")
                event_bus.emit(
                    event_bus.JOB_LOG,
                    job_id=self.job_id,
                    message=f"Loading Azubiyo page {page_num}...",
                    level="INFO",
                )

                nav_success = await self.session.navigate(page, target_url, wait_until="domcontentloaded")
                if not nav_success:
                    logger.warning(f"[{self.job_id}] Failed to navigate to {target_url}")
                    break

                await self._dismiss_cookies(page)

                # Extract job cards directly from the rendered page
                cards = await page.evaluate("""() => {
                    const list = [];
                    const seen = new Set();
                    document.querySelectorAll('.job-offer-teaser, .card-clickable, article').forEach(c => {
                        const link = c.tagName === 'A' ? c : c.querySelector('a[href*="/stellenanzeigen/"], a[href*="/ausbildung/"], a[href*="/duales-studium/"]');
                        if (!link) return;
                        const href = link.href;
                        if (!href || seen.has(href) || href.includes('/alle-') || href.includes('/stellenmarkt/')) return;
                        seen.add(href);

                        const title = c.querySelector('.h3, h3, h2')?.innerText?.trim() || '';
                        const comp = c.querySelector('.text-secondary, [class*="company"]')?.innerText?.trim() || '';
                        const loc = c.querySelector('.text-placeholder, [class*="location"]')?.innerText?.trim() || '';
                        list.push({ href, title, comp, loc });
                    });
                    return list;
                }""")

                new_cards = [c for c in cards if c["href"] not in processed_urls]
                for c in new_cards:
                    processed_urls.add(c["href"])

                logger.info(f"[{self.job_id}] Page {page_num}: Found {len(new_cards)} job cards to process.")
                event_bus.emit(
                    event_bus.JOB_LOG,
                    job_id=self.job_id,
                    message=f"Page {page_num}: Found {len(new_cards)} jobs matching query.",
                    level="INFO",
                )

                if not new_cards:
                    logger.info(f"[{self.job_id}] No more cards found on page {page_num}.")
                    break

                # Process cards concurrently with enrich_semaphore
                async def _enrich_card(card: dict) -> list[LeadRecord]:
                    if self._cancelled or not LicenseManager.can_extract():
                        return []
                    async with enrich_semaphore:
                        try:
                            return await self._process_listing_card(card)
                        except Exception as ex:
                            logger.debug(f"[{self.job_id}] Card processing error: {ex}")
                            return []

                # Schedule tasks and stream results as they finish
                tasks = [asyncio.create_task(_enrich_card(card)) for card in new_cards]

                for fut in asyncio.as_completed(tasks):
                    if self._cancelled or yielded_count >= self.config.max_results:
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        break

                    try:
                        record_list = await fut
                    except Exception as e:
                        logger.debug(f"[{self.job_id}] Task error: {e}")
                        continue

                    if not record_list:
                        continue

                    while self._paused and not self._cancelled:
                        await asyncio.sleep(0.1)
                    if self._cancelled:
                        break

                    for record in record_list:
                        if self._cancelled or yielded_count >= self.config.max_results:
                            break

                        if not LicenseManager.can_extract():
                            logger.warning(f"[{self.job_id}] Free trial limit reached.")
                            event_bus.emit(
                                event_bus.JOB_LOG,
                                job_id=self.job_id,
                                message="Free trial limit reached (20 scraps/day). Please upgrade to Professional.",
                                level="WARNING",
                            )
                            event_bus.emit(event_bus.TRIAL_LIMIT_REACHED, job_id=self.job_id)
                            return

                        # Deduplicate by company, job title, and email to prevent visual spam
                        # from employers who post the exact same job multiple times
                        email_key = str(record.email or "").strip().lower()
                        comp_key = str(record.company_name or "").strip().lower()
                        job_key = str(record.job_title or "").strip().lower()
                        dedupe_key = f"{comp_key}::{job_key}::{email_key}"
                        if dedupe_key in emitted_keys:
                            continue

                        yielded_count += 1
                        emitted_keys.add(dedupe_key)

                        LicenseManager.record_extraction()
                        logger.info(
                            f"[{self.job_id}] [{yielded_count}] {record.company_name} | "
                            f"{record.city or ''} | email={'yes' if record.email else 'no'}"
                        )
                        yield record

                page_num += 1
                await asyncio.sleep(0.3)

            logger.info(f"[{self.job_id}] Azubiyo scrape finished. Total yielded: {yielded_count}")
            event_bus.emit(
                event_bus.JOB_LOG,
                job_id=self.job_id,
                message=f"Azubiyo search completed. Found {yielded_count} leads.",
                level="SUCCESS",
            )

        except Exception as e:
            logger.error(f"[{self.job_id}] Fatal error during Azubiyo scrape: {e}", exc_info=True)
            self._total_errors += 1
            event_bus.emit(
                event_bus.JOB_LOG,
                job_id=self.job_id,
                level="ERROR",
                message=f"Azubiyo scan aborted: {str(e)}",
            )
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def _process_listing_card(self, card: dict) -> list[LeadRecord]:
        """
        Extract detailed job and company information:
        1. Fast-fetch detail page HTML.
        2. Resolve company name, address, contact person, direct email.
        3. Discover the direct online bewerbung link (/bewerben/) and external application portal.
        4. If tracking redirector (e.g. vonq.io), resolve redirect to actual destination.
        5. If still no company website, check Azubiyo company profile page (/ausbildungsbetriebe/{slug}/).
        6. Use Maps crawler logic (WebsiteEmailCrawler) to crawl the employer's domain.
        7. Return list of enriched LeadRecords.
        """
        card_url = card["href"]
        try:
            detail_html = await asyncio.to_thread(_fast_fetch_html, card_url)
            if not detail_html:
                return []

            doc = BeautifulSoup(detail_html, "html.parser")
            title_tag = doc.find("title")
            title_text = title_tag.get_text(strip=True) if title_tag else ""
            h1_tag = doc.find("h1")
            h1_text = h1_tag.get_text(strip=True) if h1_tag else ""

            job_title = h1_text or card.get("title") or self.config.job_title

            # Company name extraction
            company_name = ""
            m = re.search(r"bei\s+(.*?)\s*(?:\| Azubiyo|$)", title_text)
            if m:
                company_name = m.group(1).strip()
            if not company_name:
                company_name = card.get("comp", "").strip()

            # Address / City / Postal code
            address = ""
            postal_code = ""
            city = self.config.city or ""

            addr_el = doc.select_one(".address, address, [class*='address']")
            if addr_el:
                address = addr_el.get_text(" ", strip=True)
                plz_m = re.search(r"\b(\d{5})\s+([A-Za-zÄÖÜäöüß\s\-]+)", address)
                if plz_m:
                    postal_code = plz_m.group(1).strip()
                    city = plz_m.group(2).strip()

            if not postal_code and card.get("loc"):
                loc_raw = card["loc"]
                plz_m = re.search(r"\b(\d{5})\s+([A-Za-zÄÖÜäöüß\s\-]+)", loc_raw)
                if plz_m:
                    postal_code = plz_m.group(1).strip()
                    if not city:
                        city = plz_m.group(2).replace("(u.a.)", "").strip()

            # Phone directly on detail page
            phone = ""
            phone_a = doc.select_one('a[href^="tel:"]')
            if phone_a:
                phone = normalize_phone(phone_a["href"].replace("tel:", "").strip())

            # Email directly on detail page
            email = ""
            mail_a = doc.select_one('a[href^="mailto:"]')
            if mail_a:
                email = mail_a["href"].replace("mailto:", "").split("?")[0].strip()

            # Contact person via NLP fallback
            contact_person = ""
            try:
                contact_person = extract_contact_person_from_text(doc.get_text(separator=" ", strip=True)[:4000]) or ""
            except Exception:
                pass

            # Step A: Discover the direct online bewerbung link
            bewerben_url = None
            for a in doc.find_all("a", href=True):
                href = a["href"]
                if "bewerben" in href.lower() and not any(x in href for x in ["bewerbungstutorial", "lebenslauf", "anschreiben", "tipps"]):
                    bewerben_url = href if href.startswith("http") else f"https://www.azubiyo.de{href}"
                    break

            direct_bewerbung_target = None
            portal_emails: list[str] = []
            portal_contact_person = ""

            # Step B: If bewerben link exists, fetch it to find the target company portal
            if bewerben_url:
                bew_html, final_bew_url = await asyncio.to_thread(_fast_fetch_html_and_url, bewerben_url)
                if bew_html:
                    doc_bew = BeautifulSoup(bew_html, "html.parser")
                    for a in doc_bew.find_all("a", href=True):
                        h = a["href"]
                        if is_valid_company_url(h):
                            direct_bewerbung_target = h
                            break

            # If not found via bewerben link, look for direct external links in detail page
            if not direct_bewerbung_target:
                for a in doc.find_all("a", href=True):
                    h = a["href"]
                    if is_valid_company_url(h):
                        direct_bewerbung_target = h
                        break

            # Also check JSON-LD for company website or portal
            for sc in doc.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(sc.string or "")
                    if isinstance(data, dict):
                        org = data.get("hiringOrganization") or {}
                        if isinstance(org, dict) and is_valid_company_url(org.get("url", "")):
                            if not direct_bewerbung_target:
                                direct_bewerbung_target = org["url"]
                        desc = data.get("description", "")
                        if not direct_bewerbung_target and "<a" in desc:
                            d_soup = BeautifulSoup(desc, "html.parser")
                            for da in d_soup.find_all("a", href=True):
                                if is_valid_company_url(da["href"]):
                                    direct_bewerbung_target = da["href"]
                                    break
                except Exception:
                    pass

            # Step B.2: Employer profile page fallback on Azubiyo (/ausbildungsbetriebe/{slug}/)
            profile_website = None
            for a in doc.find_all("a", href=True):
                h = a["href"]
                if "/ausbildungsbetriebe/" in h and h.rstrip("/") != "/ausbildungsbetriebe":
                    prof_url = h if h.startswith("http") else f"https://www.azubiyo.de{h}"
                    prof_html = await asyncio.to_thread(_fast_fetch_html, prof_url, 3.0)
                    if prof_html:
                        p_soup = BeautifulSoup(prof_html, "html.parser")
                        for pa in p_soup.find_all("a", href=True):
                            ph = pa["href"]
                            if is_valid_company_url(ph):
                                profile_website = ph
                                break
                    if profile_website:
                        break

            # Step C: If direct application portal found, follow redirects (e.g. vonq.io) and inspect for contacts
            if direct_bewerbung_target:
                try:
                    portal_html, resolved_portal_url = await asyncio.to_thread(
                        _fast_fetch_html_and_url, direct_bewerbung_target, 3.5
                    )
                    if resolved_portal_url and is_valid_company_url(resolved_portal_url):
                        direct_bewerbung_target = resolved_portal_url

                    if portal_html:
                        # Extract recruiter emails from direct bewerben portal
                        p_emails = extract_emails_from_html(portal_html)
                        if p_emails:
                            portal_emails.extend(p_emails)

                        # Check JSON-LD contactPoint on the application portal
                        p_soup = BeautifulSoup(portal_html, "html.parser")
                        for sc in p_soup.find_all("script", type="application/ld+json"):
                            try:
                                p_data = json.loads(sc.string or "")
                                if isinstance(p_data, dict):
                                    cps = p_data.get("hiringOrganization", {}).get("contactPoint", [])
                                    if isinstance(cps, list):
                                        for cp in cps:
                                            if isinstance(cp, dict):
                                                cp_email = cp.get("email")
                                                cp_name = cp.get("name")
                                                if cp_email and cp_email not in portal_emails:
                                                    portal_emails.insert(0, cp_email)
                                                if cp_name and not portal_contact_person:
                                                    portal_contact_person = cp_name
                            except Exception:
                                pass
                except Exception:
                    pass

            # Derive base firma website
            best_target_url = profile_website or direct_bewerbung_target
            firma_website = ""
            if best_target_url:
                parsed = urlparse(best_target_url)
                firma_website = normalize_website(f"{parsed.scheme}://{parsed.netloc}")

            # Step D: Apply Google Maps crawler logic (WebsiteEmailCrawler) on firma website
            crawled_emails: list[str] = []
            email_source_page = best_target_url or card_url

            if self.crawler and firma_website:
                try:
                    c_emails, c_phone, c_source, _, c_contact = await self.crawler.find_all_contact_info(
                        website=firma_website,
                        company_name=company_name,
                        job_id=self.job_id,
                        bypass_cache=self.config.bypass_cache,
                        extract_social=self.config.extract_social_profiles,
                    )
                    if c_emails:
                        crawled_emails.extend(c_emails)
                    if c_phone and not phone:
                        phone = c_phone
                    if c_contact and not contact_person:
                        contact_person = c_contact
                    if c_source:
                        email_source_page = c_source
                except Exception as crawl_err:
                    logger.debug(f"[{self.job_id}] Crawler error on {firma_website}: {crawl_err}")

            if portal_contact_person and not contact_person:
                contact_person = portal_contact_person

            # Combine all discovered emails (direct recruiter emails first, then crawled)
            all_emails: list[str] = []
            if email:
                all_emails.append(email)
            for pe in portal_emails:
                if pe not in all_emails:
                    all_emails.append(pe)
            for ce in crawled_emails:
                if ce not in all_emails:
                    all_emails.append(ce)

            all_emails = deduplicate_emails(all_emails)

            primary_email = all_emails[0] if all_emails else ""

            # Check if email is required by config
            if self.config.scrape_emails and not primary_email:
                return []

            primary_record = LeadRecord(
                source_type=SourceType.AZUBIYO,
                source_url=card_url,
                search_query=self.config.job_title,
                city=city,
                postal_code=postal_code,
                company_name=company_name,
                address=address,
                phone=phone,
                email=primary_email,
                email_source_page=email_source_page,
                website=firma_website or best_target_url or "",
                contact_person=contact_person,
                job_title=job_title,
            ).normalize()

            records = [primary_record]

            # Clone records for additional emails
            for extra_email in all_emails[1:]:
                clone = LeadRecord.from_dict(primary_record.to_dict())
                clone.email = extra_email
                records.append(clone.normalize())

            if primary_email:
                event_bus.emit(
                    event_bus.JOB_LOG,
                    job_id=self.job_id,
                    message=f"Found contact for {company_name}: {primary_email}",
                    level="INFO",
                )

            return records

        except Exception as e:
            logger.warning(f"[{self.job_id}] Error processing {card_url}: {e}")
            self._total_errors += 1
            return []

# 1.1.2 build 10
