// ---------------------------------------------------------------------
// Shared helper for index.html / employee-details.html: reads
// window.HR_PERIODS (from periods.js) and dynamically loads a chosen
// month's data.js via a plain <script src> tag (works from file://,
// unlike fetch()). Used to power the Year / Month picker.
// ---------------------------------------------------------------------
(function () {
  function allFY() {
    return Object.keys(window.HR_PERIODS || {});
  }

  function monthsFor(fy) {
    return (window.HR_PERIODS && window.HR_PERIODS[fy]) || [];
  }

  function flatList() {
    const out = [];
    allFY().forEach(fy => {
      monthsFor(fy).forEach(m => out.push(Object.assign({ fy: fy }, m)));
    });
    return out;
  }

  // Picks the most recent month that is on/before today; falls back to the
  // earliest configured month if every configured month is in the future.
  function defaultEntry() {
    const list = flatList();
    if (!list.length) return null;
    const today = new Date();
    const ty = today.getFullYear(), tm = today.getMonth() + 1;
    const past = list.filter(p => (p.year < ty) || (p.year === ty && p.month <= tm));
    past.sort((a, b) => (a.year - b.year) || (a.month - b.month));
    if (past.length) return past[past.length - 1];
    const all = list.slice().sort((a, b) => (a.year - b.year) || (a.month - b.month));
    return all[0];
  }

  function findEntry(fy, folder) {
    return monthsFor(fy).find(m => m.folder === folder);
  }

  let currentScriptEl = null;

  // Loads "<folder>/data.js", which assigns window.ATTENDANCE_DATA.
  // Calls onSuccess() once loaded, or onError(err) if the file is missing
  // (e.g. an empty template month that hasn't been processed yet).
  function loadPeriod(folder, onSuccess, onError) {
    window.ATTENDANCE_DATA = null;
    if (currentScriptEl && currentScriptEl.parentNode) {
      currentScriptEl.parentNode.removeChild(currentScriptEl);
    }
    const s = document.createElement("script");
    s.src = folder + "/data.js";
    s.onload = function () {
      if (window.ATTENDANCE_DATA) onSuccess();
      else onError(new Error("data.js loaded but window.ATTENDANCE_DATA is missing"));
    };
    s.onerror = function () {
      onError(new Error("Could not load " + folder + "/data.js"));
    };
    document.body.appendChild(s);
    currentScriptEl = s;
  }

  window.HRPeriods = { allFY, monthsFor, flatList, defaultEntry, findEntry, loadPeriod };
})();
