/**
 * ZUGZWANG - Apple Design Interactive Controller
 * - Restrained Apple-style Scroll Reveal (IntersectionObserver)
 * - Pure Vanilla Lightbox Gallery Modal with keyboard & gesture navigation
 * - Client Platform/OS Auto-Detection for Recommended Download Card
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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', highlightRecommendedDownload);
  } else {
    highlightRecommendedDownload();
  }
})();
