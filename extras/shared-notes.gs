/**
 * Shared stars + notes for lineandlocker.com (Google Apps Script web app).
 *
 * Setup (one time, about 5 minutes):
 *  1. Create a new Google Sheet (any name, e.g. "Line & Locker notes").
 *  2. Extensions -> Apps Script. Delete what's there, paste this whole file.
 *  3. Change TEAM_CODE below to a secret word you and Chad will both type on the site.
 *     Put your two email addresses in ALERTS.
 *  4. Deploy -> New deployment -> type "Web app". Execute as: Me. Who has access: Anyone.
 *     Click Deploy, approve the Google permissions, and copy the Web app URL.
 *  5. Put that URL in config.toml as notes_url (or send it to Claude).
 */
const TEAM_CODE = "change-me";
const ALERTS = {
  // name typed on the site -> email of the OTHER person to alert
  // "Chucky": "chad@example.com",
  // "Gimp": "andrew@example.com",
};
const SITE = "https://lineandlocker.com";

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName("Notes");
  if (!sh) {
    sh = ss.insertSheet("Notes");
    sh.appendRow(["id", "star", "note", "by", "at", "snap"]);
    sh.getRange("C:C").setNumberFormat("@");
  }
  return sh;
}

function out_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  if ((e.parameter.key || "") !== TEAM_CODE) return out_({ok: false});
  const rows = sheet_().getDataRange().getValues().slice(1);
  const notes = {};
  rows.forEach(r => {
    if (!r[0]) return;
    let snap = null;
    try { snap = r[5] ? JSON.parse(r[5]) : null; } catch (err) {}
    notes[r[0]] = {
      star: r[1] === true || r[1] === "TRUE",
      note: String(r[2] || ""),
      by: String(r[3] || ""),
      at: r[4] instanceof Date ? r[4].toISOString() : String(r[4] || ""),
      snap: snap,
    };
  });
  return out_({ok: true, notes: notes});
}

function doPost(e) {
  const b = JSON.parse(e.postData.contents);
  if (b.key !== TEAM_CODE) return out_({ok: false});
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  let oldNote = "";
  try {
    const sh = sheet_();
    const last = sh.getLastRow();
    const ids = last > 0 ? sh.getRange(1, 1, last, 1).getValues().map(r => r[0]) : [];
    const i = ids.indexOf(b.id);
    if (i > 0) oldNote = String(sh.getRange(i + 1, 3).getValue() || "");
    const row = [b.id, !!b.star, String(b.note || ""), String(b.by || ""), new Date().toISOString(), b.snap ? JSON.stringify(b.snap) : ""];
    if (i > 0) sh.getRange(i + 1, 1, 1, 6).setValues([row]);
    else sh.appendRow(row);
  } finally {
    lock.releaseLock();
  }
  const to = ALERTS[b.by];
  if (to && b.note && b.note !== oldNote) {
    const s = b.snap || {};
    MailApp.sendEmail({
      to: to,
      subject: `${b.by} added a note: ${s.fac || "storage auction"}`,
      body: `${b.by} wrote:\n\n${b.note}\n\n${s.fac || ""}, ${s.city || ""} · ${s.size || ""} · bid $${s.bid == null ? "?" : s.bid}\n${s.url || ""}\n\nAll watched auctions: ${SITE}/#w=1`,
    });
  }
  return out_({ok: true});
}

/**
 * Hourly kick for the bid updates (GitHub's own schedule is unreliable for this repo).
 * Setup: add a Script property GH_TOKEN (Project Settings -> Script properties) holding a
 * fine-grained GitHub token for this repo only, with "Actions: Read and write".
 * Then Triggers (alarm-clock icon) -> Add Trigger -> kickUpdate, Time-driven, Hour timer, Every hour.
 */
function kickUpdate() {
  const hour = Number(Utilities.formatDate(new Date(), "America/Los_Angeles", "H"));
  if (hour < 6 || hour > 22) return;  // 6 AM to 10 PM Pacific
  const token = PropertiesService.getScriptProperties().getProperty("GH_TOKEN");
  if (!token) throw new Error("Add the GH_TOKEN script property first.");
  const res = UrlFetchApp.fetch(
    "https://api.github.com/repos/ad204774/storage-auction-tracker/actions/workflows/daily.yml/dispatches", {
      method: "post",
      contentType: "application/json",
      headers: {Authorization: "Bearer " + token, Accept: "application/vnd.github+json"},
      payload: JSON.stringify({ref: "main", inputs: {email: hour === 6 ? "yes" : "no"}}),
      muteHttpExceptions: true,
    });
  if (res.getResponseCode() !== 204) throw new Error("GitHub said " + res.getResponseCode() + ": " + res.getContentText());
}
