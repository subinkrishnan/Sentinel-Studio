'use strict';
// Demonstration only. Site access remains controlled by the hosting platform.
(() => {
  const sessionKey = 'sentinel-demo-session';
  const login = document.getElementById('login-screen');
  const portal = document.getElementById('studio-portal');
  const form = document.getElementById('login-form');
  const error = document.getElementById('login-error');
  const password = document.getElementById('login-password');
  const profile = document.getElementById('profile-menu');
  function showStudio() {
    login.hidden = true;
    portal.hidden = false;
  }
  const runnerSession = document.body.dataset.runnerSession === 'true';
  if (runnerSession) showStudio();
  try { if (sessionStorage.getItem(sessionKey) === 'sunil.demo') showStudio(); } catch (_) {}
  form.addEventListener('submit', event => {
    event.preventDefault();
    const user = document.getElementById('login-user');
    if (user.value.trim() !== 'sunil.demo' || password.value !== 'AtomaDemo2026!') {
      error.textContent = 'User ID or password is incorrect. Please try again.';
      error.hidden = false;
      password.value = '';
      password.focus();
      return;
    }
    try { sessionStorage.setItem(sessionKey, 'sunil.demo'); } catch (_) {}
    error.hidden = true;
    password.value = '';
    location.hash = '#brief';
    showStudio();
    document.querySelector('nav [data-page="brief"]').focus();
  });
  document.getElementById('demo-logout').addEventListener('click', async () => {
    if (runnerSession) {
      const response = await fetch('/api/logout', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
      if (!response.ok) return;
    }
    try { sessionStorage.removeItem(sessionKey); } catch (_) {}
    location.replace(location.pathname + location.search + '#brief');
    location.reload();
  });
  document.addEventListener('click', event => {
    if (!profile.contains(event.target)) profile.open = false;
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && profile.open) {
      profile.open = false;
      profile.querySelector('summary').focus();
    }
  });
})();

