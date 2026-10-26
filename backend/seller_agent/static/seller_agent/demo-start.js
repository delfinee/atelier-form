(() => {
  const form = document.getElementById('open-demo');
  if (form && document.body.dataset.autoOpen === 'true') form.requestSubmit();
})();
