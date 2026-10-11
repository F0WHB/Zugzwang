/**
 * ZUGZWANG - Apple Design Interactive Controller
 * - Restrained Apple-style Scroll Reveal (IntersectionObserver)
 * - Pure Vanilla Lightbox Gallery Modal with keyboard & gesture navigation
 * - Client Platform/OS Auto-Detection for Recommended Download Card
 * - Interactive Hero Showcase Tab Switcher
 * - Smooth Accessible FAQ Accordion
 */

(function () {
  'use strict';

  // 1. Apple-Style Scroll Reveal
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in-view');
          obs.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -40px 0px'
    });

    document.querySelectorAll('.apple-reveal').forEach(el => observer.observe(el));
  } else {
    document.querySelectorAll('.apple-reveal').forEach(el => el.classList.add('in-view'));
  }

  // 2. Lightbox Gallery Controller
  const lb = document.getElementById('lightbox');
  if (lb) {
    const img = lb.querySelector('.lb-image');
    const count = lb.querySelector('.lb-count');
    const closeBtn = lb.querySelector('.lb-close');
    const prevBtn = lb.querySelector('.lb-prev');
    const nextBtn = lb.querySelector('.lb-next');

    let current = [];
    let index = 0;

    function gallerySources(group) {
      return Array.from(group.querySelectorAll('img')).map(el => el.getAttribute('data-full') || el.src);
    }

    function open(sources, startIndex) {
      current = sources;
      index = startIndex;
      render();
      lb.classList.remove('hidden');
      lb.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
    }

    function close() {
      lb.classList.add('hidden');
      lb.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
    }

    function step(delta) {
      if (!current.length) return;
      index = (index + delta + current.length) % current.length;
      render();
    }

    function render() {
      if (!current.length) return;
      img.src = current[index];
      if (count) {
        count.textContent = (index + 1) + ' / ' + current.length;
      }
    }

    // Attach click listeners to gallery elements
    document.querySelectorAll('[data-gallery]').forEach(group => {
      const imgs = group.querySelectorAll('img');
      imgs.forEach((el, i) => {
        el.style.cursor = 'zoom-in';
        el.addEventListener('click', (e) => {
          e.preventDefault();
          open(gallerySources(group), i);
        });
      });
    });

    if (closeBtn) closeBtn.addEventListener('click', close);
    if (prevBtn) prevBtn.addEventListener('click', () => step(-1));
    if (nextBtn) nextBtn.addEventListener('click', () => step(1));

    // Close when clicking outside image
    lb.addEventListener('click', (e) => {
      if (e.target === lb) close();
    });

    // Keyboard navigation
    window.addEventListener('keydown', (e) => {
      if (lb.classList.contains('hidden')) return;
      if (e.key === 'Escape') close();
      if (e.key === 'ArrowLeft') step(-1);
      if (e.key === 'ArrowRight') step(1);
    });
  }

  // 3. Platform / OS Auto-Detection for Downloads
  function highlightRecommendedDownload() {
    try {
      const userAgent = window.navigator.userAgent || '';
      const platform = window.navigator.platform || '';
      let targetId = null;

      if (/Macintosh|MacIntel|MacPPC|Mac68K/i.test(platform) || /Mac OS X/i.test(userAgent)) {
        targetId = 'download-macos';
      } else if (/Win32|Win64|Windows|WinCE/i.test(platform) || /Windows NT/i.test(userAgent)) {
        targetId = 'download-windows';
      } else if (/Linux/i.test(platform) || /Linux/i.test(userAgent)) {
        targetId = 'download-linux';
      }

      if (targetId) {
        const card = document.getElementById(targetId);
        if (card && !card.querySelector('.recommended-tag')) {
          card.classList.add('card-recommended');
          const tag = document.createElement('span');
          tag.className = 'recommended-tag';
          tag.textContent = 'Recommended for you';
          card.prepend(tag);
        }
      }
    } catch (err) {
      // Fallback silently if platform info is restricted
    }
  }

  // 4. Hero Showcase Window Tab Switcher
  function initHeroTabs() {
    const heroTabs = document.querySelectorAll('.hero-tab');
    const heroImg = document.getElementById('hero-preview-img');
    const heroTitle = document.getElementById('hero-window-title');

    const heroScreenshots = {
      'hero-img-search': {
        src: 'images/screenshot_search_clean.png',
        title: 'ZUGZWANG — Search Ausbildung & Jobs by City and Radius'
      },
      'hero-img-monitor': {
        src: 'images/screenshot_monitor_clean.png',
        title: 'ZUGZWANG — Live Search Across All German Portals'
      },
      'hero-img-dashboard': {
        src: 'images/screenshot_dashboard_clean.png',
        title: 'ZUGZWANG — Your Search Overview & Discovered Openings'
      },
      'hero-img-results': {
        src: 'images/screenshot_results_clean.png',
        title: 'ZUGZWANG — Direct Recruiter Contacts & Phone Numbers'
      },
      'hero-img-letter': {
        src: 'images/screenshot_edit_clean.png',
        title: 'ZUGZWANG — Automatic German Cover Letter Creator (DIN 5008)'
      },
      'hero-img-send': {
        src: 'images/screenshot_send_clean.png',
        title: 'ZUGZWANG — Send Applications Directly from Your Own Email'
      }
    };

    heroTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        heroTabs.forEach(t => {
          t.classList.remove('active');
          t.setAttribute('aria-selected', 'false');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');

        const targetKey = tab.getAttribute('data-target');
        const data = heroScreenshots[targetKey];
        if (data && heroImg) {
          heroImg.style.opacity = '0';
          heroImg.style.transform = 'scale(0.995)';

          const temp = new Image();
          temp.onload = () => {
            heroImg.src = data.src;
            if (heroTitle) heroTitle.textContent = data.title;
            requestAnimationFrame(() => {
              heroImg.style.opacity = '1';
              heroImg.style.transform = 'scale(1)';
            });
          };
          temp.src = data.src;
        }
      });
    });
  }

  // 5. Accessible FAQ Accordion
  function initFaq() {
    const items = document.querySelectorAll('.faq-item');
    items.forEach(item => {
      const trigger = item.querySelector('.faq-trigger');
      if (!trigger) return;

      trigger.addEventListener('click', () => {
        const isOpen = item.classList.contains('open');
        items.forEach(i => {
          i.classList.remove('open');
          const btn = i.querySelector('.faq-trigger');
          if (btn) btn.setAttribute('aria-expanded', 'false');
        });
        if (!isOpen) {
          item.classList.add('open');
          trigger.setAttribute('aria-expanded', 'true');
        }
      });
    });
  }

  // 6. Popular Ausbildung Search Teaser Controller
  function initTeaserPills() {
    const pills = document.querySelectorAll('.teaser-pill');
    const feedbackText = document.getElementById('teaser-feedback-text');

    pills.forEach(pill => {
      pill.addEventListener('click', () => {
        pills.forEach(p => p.classList.remove('active'));
        pill.classList.add('active');

        const role = pill.getAttribute('data-role') || '';
        const city = pill.getAttribute('data-city') || '';
        const count = pill.getAttribute('data-count') || '30+';
        const tabTarget = pill.getAttribute('data-tab');

        if (feedbackText) {
          feedbackText.style.opacity = '0';
          setTimeout(() => {
            feedbackText.innerHTML = `<strong>${count} direct employer contacts</strong> discovered for ${role} in ${city} &bull; Ready to generate German Anschreiben`;
            feedbackText.style.opacity = '1';
          }, 120);
        }

        // Switch to the matching hero screenshot tab if present
        if (tabTarget) {
          const matchingTab = document.querySelector(`.hero-tab[data-target="${tabTarget}"]`);
          if (matchingTab && !matchingTab.classList.contains('active')) {
            matchingTab.click();
          }
        }
      });
    });
  }

  // 7. Floating Apple Quick Action Dock Pill Controller
  function initFloatingBar() {
    const bar = document.getElementById('floating-bar');
    const topBtn = document.getElementById('btn-back-to-top');
    if (!bar) return;

    let ticking = false;
    window.addEventListener('scroll', () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          if (window.scrollY > 420) {
            bar.classList.remove('hidden');
          } else {
            bar.classList.add('hidden');
          }
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });

    if (topBtn) {
      topBtn.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }
  }

  // 8. Dynamic OS-specific Download Button in Hero
  function initHeroDownloadButton() {
    const btn = document.getElementById('hero-download-btn');
    if (!btn) return;

    try {
      const userAgent = window.navigator.userAgent || '';
      const platform = window.navigator.platform || '';
      let osLabel = 'Download Free App';
      let targetHref = '#downloads';

      if (/Macintosh|MacIntel|MacPPC|Mac68K/i.test(platform) || /Mac OS X/i.test(userAgent)) {
        osLabel = 'Download for Mac (v1.2.2 .dmg)';
        targetHref = 'https://github.com/F0WHB/Zugzwang/releases/latest';
      } else if (/Win32|Win64|Windows|WinCE/i.test(platform) || /Windows NT/i.test(userAgent)) {
        osLabel = 'Download for Windows (v1.2.2 .exe)';
        targetHref = 'https://github.com/F0WHB/Zugzwang/releases/latest';
      } else if (/Linux/i.test(platform) || /Linux/i.test(userAgent)) {
        osLabel = 'Download for Linux (v1.2.2)';
        targetHref = 'https://github.com/F0WHB/Zugzwang/releases/latest';
      }

      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="7 10 12 15 17 10"></polyline>
          <line x1="12" y1="15" x2="12" y2="3"></line>
        </svg>
        ${osLabel}
      `;
      btn.href = targetHref;
    } catch (e) {}
  }

  // 9. Interactive DIN 5008 Cover Letter Live Simulator
  function initCoverLetterSimulator() {
    const companyInput = document.getElementById('sim-input-company');
    const addressInput = document.getElementById('sim-input-address');
    const cityInput = document.getElementById('sim-input-city');
    const roleInput = document.getElementById('sim-input-role');
    const contactInput = document.getElementById('sim-input-contact');
    const copyBtn = document.getElementById('sim-copy-btn');

    if (!companyInput || !roleInput) return;

    function updatePreview() {
      const company = companyInput.value.trim() || 'Musterfirma GmbH';
      const address = addressInput ? addressInput.value.trim() || 'Hauptstraße 42' : 'Hauptstraße 42';
      const city = cityInput.value.trim() || '10115 Berlin';
      const role = roleInput.value.trim() || 'Fachinformatiker für Anwendungsentwicklung';
      const contact = contactInput.value.trim() || 'Frau Schmidt';

      const prevCompany = document.getElementById('sim-preview-company');
      const prevAddress = document.getElementById('sim-preview-address');
      const prevCity = document.getElementById('sim-preview-city');
      const prevSubject = document.getElementById('sim-preview-subject');
      const prevSalutation = document.getElementById('sim-preview-salutation');
      const prevRoleBody = document.getElementById('sim-preview-role-body');

      if (prevCompany) prevCompany.textContent = company;
      if (prevAddress) prevAddress.textContent = address;
      if (prevCity) prevCity.textContent = city;
      if (prevSubject) prevSubject.textContent = `Bewerbung um einen Ausbildungsplatz als ${role}`;
      if (prevSalutation) prevSalutation.textContent = `Sehr geehrte(r) ${contact},`;
      if (prevRoleBody) prevRoleBody.textContent = role;
    }

    [companyInput, addressInput, cityInput, roleInput, contactInput].forEach(inp => {
      if (inp) {
        inp.addEventListener('input', updatePreview);
      }
    });

    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        const paper = document.getElementById('sim-paper-content');
        if (!paper) return;
        const textToCopy = paper.innerText || paper.textContent || '';
        navigator.clipboard.writeText(textToCopy).then(() => {
          copyBtn.classList.add('copied');
          copyBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            Kopiert!
          `;
          setTimeout(() => {
            copyBtn.classList.remove('copied');
            copyBtn.innerHTML = `
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              Text kopieren
            `;
          }, 2000);
        });
      });
    }

    updatePreview();
  }

  // 10. Changelog Modal Controller
  function initChangelogModal() {
    const modal = document.getElementById('changelog-modal');
    const openBtns = document.querySelectorAll('.open-changelog-trigger');
    const closeBtn = document.getElementById('changelog-modal-close');

    if (!modal) return;

    function openModal(e) {
      if (e) e.preventDefault();
      modal.classList.add('active');
      modal.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
    }

    function closeModal() {
      modal.classList.remove('active');
      modal.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
    }

    openBtns.forEach(b => b.addEventListener('click', openModal));
    if (closeBtn) closeBtn.addEventListener('click', closeModal);

    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modal.classList.contains('active')) {
        closeModal();
      }
    });
  }

  // Initialize on load
  function initAll() {
    highlightRecommendedDownload();
    initHeroTabs();
    initFaq();
    initTeaserPills();
    initFloatingBar();
    initHeroDownloadButton();
    initCoverLetterSimulator();
    initChangelogModal();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
