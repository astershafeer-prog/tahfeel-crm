// TASK 1.4: lightweight country-code selector for phone inputs.
// Defaults to +971 (UAE). Switching the selector only rewrites the input
// while it still looks untouched (just a "+<code> " prefix) — once the user
// has typed real digits, switching the selector never clobbers what they typed.
// Server-side normalization (normalize_phone_e164 in app.py) is the real
// safety net; this is just so staff don't have to hand-type "+971" every time
// and so a foreign number requires a deliberate selector change, not a typo.
var PHONE_COUNTRY_CODES = [
  ['971', '🇦🇪 UAE +971'],
  ['966', '🇸🇦 KSA +966'],
  ['968', '🇴🇲 Oman +968'],
  ['973', '🇧🇭 Bahrain +973'],
  ['974', '🇶🇦 Qatar +974'],
  ['965', '🇰🇼 Kuwait +965'],
  ['91',  '🇮🇳 India +91'],
  ['92',  '🇵🇰 Pakistan +92'],
  ['63',  '🇵🇭 Philippines +63'],
  ['20',  '🇪🇬 Egypt +20'],
  ['44',  '🇬🇧 UK +44'],
  ['1',   '🇺🇸/🇨🇦 US/Canada +1'],
];

function initPhoneCountry(inputEl, selectEl, defaultCode) {
  defaultCode = defaultCode || '971';
  if (!inputEl || !selectEl) return;

  selectEl.innerHTML = '';
  PHONE_COUNTRY_CODES.forEach(function(pair) {
    var opt = document.createElement('option');
    opt.value = pair[0];
    opt.textContent = pair[1];
    if (pair[0] === defaultCode) opt.selected = true;
    selectEl.appendChild(opt);
  });

  function prefix() { return '+' + selectEl.value + ' '; }
  function looksUntouched(v) { return /^\+\d*\s*$/.test((v || '').trim()); }

  if (!inputEl.value || looksUntouched(inputEl.value)) {
    inputEl.value = prefix();
  }

  selectEl.addEventListener('change', function() {
    if (looksUntouched(inputEl.value)) {
      inputEl.value = prefix();
    }
  });

  inputEl.addEventListener('focus', function() {
    if (looksUntouched(this.value)) {
      var len = this.value.length;
      this.setSelectionRange(len, len);
    }
  });

  inputEl.addEventListener('keydown', function(e) {
    if ((e.key === 'Backspace' || e.key === 'Delete') && this.value === prefix()) {
      e.preventDefault();
    }
  });
}
