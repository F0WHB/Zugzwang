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
        title: 'ZUGZWANG — Search Configuration & Radial Filtering'
      },
      'hero-img-monitor': {
        src: 'images/screenshot_monitor_clean.png',
        title: 'ZUGZWANG — Live Web Scraping & Multi-Threaded Monitor'
      },
      'hero-img-dashboard': {
        src: 'images/screenshot_dashboard_clean.png',
        title: 'ZUGZWANG — Executive Discovery Dashboard'
      },
      'hero-img-results': {
        src: 'images/screenshot_results_clean.png',
        title: 'ZUGZWANG — Enriched Hiring Manager Results Grid'
      },
      'hero-img-letter': {
        src: 'images/screenshot_edit_clean.png',
        title: 'ZUGZWANG — German Motivation Letter Studio (DIN 5008)'
      },
      'hero-img-send': {
        src: 'images/screenshot_send_clean.png',
        title: 'ZUGZWANG — Safe Rate-Limited Email Broadcast Console'
      },
      'hero-img-logs': {
        src: 'images/screenshot_logs_clean.png',
        title: 'ZUGZWANG — Real-Time Diagnostics & HTTP Log Stream'
      },
      'hero-img-settings': {
        src: 'images/screenshot_settings_clean.png',
        title: 'ZUGZWANG — Local Hardware PIN Lock & Preferences'
      }
    };

    heroTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        heroTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const targetKey = tab.getAttribute('data-target');
        const data = heroScreenshots[targetKey];
        if (data && heroImg) {
          heroImg.style.opacity = '0.35';
          setTimeout(() => {
            heroImg.src = data.src;
            if (heroTitle) heroTitle.textContent = data.title;
            heroImg.style.opacity = '1';
          }, 120);
        }
      });
    });
  }

  // 5. FAQ Accordion
  function initFaq() {
    document.querySelectorAll('.faq-trigger').forEach(trigger => {
      trigger.addEventListener('click', () => {
        const item = trigger.closest('.faq-item');
        const isOpen = item.classList.contains('open');
        document.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));
        if (!isOpen) {
          item.classList.add('open');
        }
      });
    });
  }

  // Initialize on load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      highlightRecommendedDownload();
      initHeroTabs();
      initFaq();
    });
  } else {
    highlightRecommendedDownload();
    initHeroTabs();
    initFaq();
  }
})();
