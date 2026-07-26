// TASK 1.5: Emirates ID live-format mask — 784-XXXX-XXXXXXX-X (15 digits, must
// start 784). Invalid entries get an amber warning but are NEVER blocked from
// saving — staff sometimes need to record a partial/pending number.
function initEidMask(inputEl, warningEl) {
  if (!inputEl) return;

  function format(digits) {
    var parts = [];
    if (digits.length > 0) parts.push(digits.slice(0, 3));
    if (digits.length > 3) parts.push(digits.slice(3, 7));
    if (digits.length > 7) parts.push(digits.slice(7, 14));
    if (digits.length > 14) parts.push(digits.slice(14, 15));
    return parts.join('-');
  }

  function isValid(digits) {
    return digits.length === 15 && digits.startsWith('784');
  }

  function refresh() {
    var digits = inputEl.value.replace(/\D/g, '').slice(0, 15);
    inputEl.value = format(digits);
    var complete = digits.length > 0;
    var valid = isValid(digits);
    if (warningEl) {
      warningEl.style.display = (complete && !valid) ? 'block' : 'none';
    }
  }

  inputEl.addEventListener('input', refresh);
  if (inputEl.value) refresh();
}
