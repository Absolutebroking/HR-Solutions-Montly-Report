// ---------------------------------------------------------------------
// Manifest of fiscal years and months for the attendance dashboard.
//
// Each fiscal year is a key like "2026-2027" (April 2026 – March 2027).
// Each entry in its list is one month folder: { label, folder, year, month }
//   - label:  text shown in the Month dropdown
//   - folder: path to that month's folder (must match an actual folder
//             containing punches.csv etc., relative to this file)
//   - year/month: the calendar year/month (month = 1-12), used only to
//             pick a sensible default when the page first loads
//
// TO ADD A NEW MONTH to an existing fiscal year: create the folder
// (copy an empty month folder's CSVs as a template), then add one line
// below pointing to it.
//
// TO ADD A NEW FISCAL YEAR: create a new top-level folder (e.g.
// "2027-2028") with its 12 month subfolders, then add a new key below,
// following the same pattern as "2026-2027".
// ---------------------------------------------------------------------
window.HR_PERIODS = {
  "2026-2027": [
    { label: "April 2026",     folder: "2026-2027/April-2026",     year: 2026, month: 4  },
    { label: "May 2026",       folder: "2026-2027/May-2026",       year: 2026, month: 5  },
    { label: "June 2026",      folder: "2026-2027/June-2026",      year: 2026, month: 6  },
    { label: "July 2026",      folder: "2026-2027/July-2026",      year: 2026, month: 7  },
    { label: "August 2026",    folder: "2026-2027/August-2026",    year: 2026, month: 8  },
    { label: "September 2026", folder: "2026-2027/September-2026", year: 2026, month: 9  },
    { label: "October 2026",   folder: "2026-2027/October-2026",   year: 2026, month: 10 },
    { label: "November 2026",  folder: "2026-2027/November-2026",  year: 2026, month: 11 },
    { label: "December 2026",  folder: "2026-2027/December-2026",  year: 2026, month: 12 },
    { label: "January 2027",   folder: "2026-2027/January-2027",   year: 2027, month: 1  },
    { label: "February 2027",  folder: "2026-2027/February-2027",  year: 2027, month: 2  },
    { label: "March 2027",     folder: "2026-2027/March-2027",     year: 2027, month: 3  }
  ]
  // "2027-2028": [
  //   { label: "April 2027", folder: "2027-2028/April-2027", year: 2027, month: 4 },
  //   ... etc
  // ]
};
