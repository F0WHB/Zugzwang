/**
 * ZUGZWANG - Website Interactive Controller
 * Features:
 * - Pure Vanilla Lightbox Gallery (SparkDev pattern) with keyboard & gesture navigation
 * - Theme Switcher (Obsidian Dark / Crisp Ambient Light) with localStorage sync
 * - Smooth scroll navigation
 */

(function () {
  'use strict';

  // 1. Theme Management
  const themeToggleBtn = document.getElementById('theme-toggle');
  const storedTheme = localStorage.getItem('zugzwang-theme');
  const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  const initialTheme = storedTheme || (systemPrefersDark ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', initialTheme);
  updateThemeIcon(initialTheme);

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', newTheme);
      localStorage.setItem('zugzwang-theme', newTheme);
      updateThemeIcon(newTheme);
    });
  }

  function updateThemeIcon(theme) {
    if (!themeToggleBtn) return;
    if (theme === 'dark') {
      // Moon icon
      themeToggleBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      `;
      themeToggleBtn.setAttribute('title', 'Switch to Daylight Theme');
      themeToggleBtn.setAttribute('aria-label', 'Switch to Daylight Theme');
    } else {
      // Sun icon
      themeToggleBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"></circle>
          <line x1="12" y1="1" x2="12" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="23"></line>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
          <line x1="1" y1="12" x2="3" y2="12"></line>
          <line x1="21" y1="12" x2="23" y2="12"></line>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
        </svg>
      `;
      themeToggleBtn.setAttribute('title', 'Switch to Obsidian Theme');
      themeToggleBtn.setAttribute('aria-label', 'Switch to Obsidian Theme');
    }
  }

  // 2. Lightbox / Image Gallery (SparkDev Pattern)
  const lb = document.getElementById('lightbox');
  if (lb) {
    const img = lb.querySelector('.lb-image');
    const count = lb.querySelector('.lb-count');
    let current = [];
    let index = 0;

    function gallerySources(group) {
      return [...group.querySelectorAll('img')].map(el => el.getAttribute('data-full') || el.src);
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
      count.textContent = (index + 1) + ' / ' + current.length;
    }

    // Attach click listeners to all gallery groups
    document.querySelectorAll('[data-gallery]').forEach(group => {
      const sources = gallerySources(group);
      group.querySelectorAll('img').forEach((el) => {
        el.addEventListener('click', () => {
          const targetSrc = el.getAttribute('data-full') || el.src;
          const idx = sources.indexOf(targetSrc);
          open(sources, idx >= 0 ? idx : 0);
        });
      });
    });

    lb.querySelector('.lb-close').addEventListener('click', close);
    lb.querySelector('.lb-prev').addEventListener('click', () => step(-1));
    lb.querySelector('.lb-next').addEventListener('click', () => step(+1));
    
    lb.addEventListener('click', e => {
      if (e.target === lb) close();
    });

    document.addEventListener('keydown', e => {
      if (lb.classList.contains('hidden')) return;
      if (e.key === 'Escape') close();
      else if (e.key === 'ArrowLeft') step(-1);
      else if (e.key === 'ArrowRight') step(+1);
    });
  }
})();
