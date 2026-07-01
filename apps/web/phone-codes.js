/** Country dial codes — Dubai/UAE (+971) first as default market */
window.TRAVELAI_DIAL_CODES = [
  { code: "+971", label: "🇦🇪 UAE +971", country: "uae", maxLen: 9 },
  { code: "+91", label: "🇮🇳 India +91", country: "india", maxLen: 10 },
  { code: "+966", label: "🇸🇦 Saudi +966", country: "uae", maxLen: 9 },
  { code: "+974", label: "🇶🇦 Qatar +974", country: "uae", maxLen: 8 },
  { code: "+968", label: "🇴🇲 Oman +968", country: "uae", maxLen: 8 },
  { code: "+973", label: "🇧🇭 Bahrain +973", country: "uae", maxLen: 8 },
  { code: "+965", label: "🇰🇼 Kuwait +965", country: "uae", maxLen: 8 },
  { code: "+1", label: "🇺🇸 US +1", country: "uae", maxLen: 10 },
  { code: "+44", label: "🇬🇧 UK +44", country: "uae", maxLen: 10 },
  { code: "+61", label: "🇦🇺 Australia +61", country: "uae", maxLen: 9 },
  { code: "+65", label: "🇸🇬 Singapore +65", country: "uae", maxLen: 8 },
];

window.buildCountryCodeOptions = function buildCountryCodeOptions(selected = "+971") {
  return window.TRAVELAI_DIAL_CODES.map(
    (c) => `<option value="${c.code}" ${c.code === selected ? "selected" : ""}>${c.label}</option>`
  ).join("");
};

window.buildPhoneFieldHtml = function buildPhoneFieldHtml(defaultCode = "+971") {
  return `<div class="phone-row">
    <select name="country_code" class="country-code" aria-label="Country code">${window.buildCountryCodeOptions(defaultCode)}</select>
    <input name="phone_local" class="phone-local" type="tel" inputmode="numeric" pattern="[0-9]*" placeholder="501234567" maxlength="12" required autocomplete="tel-national" />
  </div>`;
};
