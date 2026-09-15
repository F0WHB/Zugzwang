/**
 * ZUGZWANG - Apple Design Interactive Controller
 * - Restrained Apple-style Scroll Reveal (IntersectionObserver)
 * - Pure Vanilla Lightbox Gallery Modal with keyboard & gesture navigation
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
})();
