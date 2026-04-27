# Changelog

All notable changes to DT-Verwaltung are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [1.4.7] – 2026-04-27

### Changed
- Contracts tab (Kunden → Verträge): merged 2-party and 3-party escrow contract forms into a single unified card with a type-selector dropdown — cleaner layout, one place for all contracts
- Contract preview backgrounds are now always white (`background:#fff; color:#000`), independent of the app's dark/light theme
- `vtTypChange()` JS function toggles between `vt-panel-2p` and `vt-panel-3p` panels on dropdown change
- `applyLang()` now rebuilds `vt-typ-select` options on language switch (DE/EN)
- Added TRANS keys: `lbl_vt_typ_2p` (2-Party Storage Contract), `lbl_vt_typ_3p` (3-Party Escrow Contract)

---

## [1.4.6] – 2026-04-27

### Added
- **Escrow-Vertragsvorlage (3 Parteien)** — new contract template form in the Verträge sub-tab: select Auftraggeber (Party 2), Haupt-Eigentümer (Party 3), optional Neben-Eigentümer (Party 3b), enter contract number and release conditions, live preview + print. Generates a bilingual 4-§ escrow contract with letterhead, party table, and signature blocks for all three parties. New function `genVertragEscrowHtml()` + `vtEscrowVorschauUpdate()` + `vtEscrowDrucken()`
- **Szenario B text corrected**: "3 Firmen" → "2 Firmen" (the two customer-side companies in the escrow: depositor + beneficiary)
- 36 new TRANS keys covering all newly translated strings

### Fixed
- **100 % DE/EN coverage — Tresor form**: all 15 labels and buttons in the safe/cabinet registration form (Bezeichnung/Name, Hersteller, Modell, Seriennummer, Kaufdatum, Kaufpreis, Letzter Wartungstermin, Standort, Stadt, Etage, Raum, Notizen, PDF hochladen, Abbrechen, Speichern) now carry `data-i18n`
- **Dashboard**: "🔒 Tresor-Wartungstermine" heading and "Keine anstehenden Wartungstermine" empty state now translated
- **Invoice template preview**: "Rechnung" heading + table column headers (Bezeichnung, Preis, Rabatt, Betrag) now `data-i18n`
- **Rechnung button**: "Drucken & Speichern" now uses `data-i18n="lbl_drucken_speichern"` (key already existed, attribute was missing)
- **Eingangsprotokoll preview**: "Protokoll-Nr.:", "Bezeichnung / Typ" row, "Unterschrift Kunde", "Unterschrift Bearbeiter" now `data-i18n`
- **Contract preview**: "Auftraggeber" placeholder now `data-i18n`
- **Admin tab**: "👤 Benutzer & Rollen" now `data-i18n`

---

## [1.4.5] – 2026-04-26

### Fixed
- **100 % DE/EN coverage — complete** — all remaining German strings found in final live verification are now translated:
  - Mengenrabatt info text + table headers ("Ab (Stück)", "Rabatt (%)", "Bezeichnung") now carry `data-i18n` using existing TRANS keys
  - Templates: "Fußzeile, Bankdaten und Steuerinformationen werden im Admin-Bereich verwaltet." → `lbl_tpl_fuss_info`
  - Templates: "Logo und Firmendaten werden vom Rechnungs-Template übernommen." (Übergabe + Eingang templates) → `lbl_tpl_logo_info` (also fixes typo "uebernommen")
  - Templates: "Logo und Firmendaten … Die §-Texte sind Vorlagen …" (Vertrag template) → `lbl_tpl_logo_info_v`
  - Template preview headings: "Übergabeprotokoll" and "Eingangsprotokoll – Datenträger-Einlagerung" → `data-i18n`
  - Contract preview: "§ 2 Vertragslaufzeit", "Kündigungsfrist", "§ 3 Eingelagerte Datenträger", "Liste wird beim Drucken aus den Kundendaten befüllt" → `data-i18n` spans
  - Signature labels in static contract preview: "Ort, Datum", "Unterschrift Lagerbetreiber", "Unterschrift Auftraggeber" → `data-i18n`
- **`genVertragHtml()` JS fully translated** — all §-headings (§ 1–§ 7), Laufzeit/Kündigungsfrist labels, DT table column headers, empty DT fallback text, and signature labels now use `_lang==='en'?...:...` ternaries
- 14 new TRANS keys added: `lbl_mg_info`, `lbl_tpl_fuss_info`, `lbl_tpl_logo_info`, `lbl_tpl_logo_info_v`, `lbl_ue_heading`, `lbl_ep_heading`, `lbl_vt_par2_heading`, `lbl_vt_par3_heading`, `lbl_vt_dt_info`, `lbl_ort_datum`, `lbl_sig_lager`, `lbl_sig_ag`, `lbl_vt_laufzeit_info`, `lbl_vt_kfrist_info`

---

## [1.4.4] – 2026-04-26

### Added
- **100 % DE/EN coverage — final strings** — all remaining German strings from live v1.4.3 verification translated:
  - Tresor form: "Wartungskosten jährlich", "Nächster Wartungstermin", "Gebäude"
  - Kunden tab: "📄 Verträge" sub-tab button; "Haupt-Eigentümer" / "Neben-Eigentümer" escrow field labels
  - DT form + edit overlay: "Firma" label, all three escrow labels (Haupt-/Neben-Eigentümer, Rechnungsempfänger) with hint spans
  - Static empty states: "Keine Datenträger", "Noch keine archivierten Datenträger", "Keine abgeschlossenen Übergaben" now carry `data-i18n`
  - Übergabe `u-kunden_id` initial option text corrected to use `opt_firma_waehlen`
  - Templates contract editor: "§ 2 Laufzeit & Kündigung", "§ 3 Entgelt", "Standardlaufzeit", "Kündigungsfrist" labels
- **JS string fixes** — `vt-v-kunden_id` option rebuild, Tresor detail view `dl()` labels (Wartungskosten, Wartungstermine), invoice "Keine Datenträger im Abrechnungszeitraum" all use `t()` / `ta()`
- **`applyLang()` additions** — escrow select empty options ("gleiche Firma" / "keiner") updated on language switch
- 22 new TRANS keys added

---

## [1.4.3] – 2026-04-26

### Added
- **100 % DE/EN coverage — final round** — all remaining German strings identified in live verification are now translated:
  - Übergabe tab: "Schritt 1" stitle, "Firma" label, "Vorschau" / "Formular" buttons, "Firma wählen" empty state, "Weiter zu Schritt 2" button, "Ausstehende Übergabe:" label
  - Rechnung tab: "Rabatt" section heading, "Vorschau" button and stitle, "Alle löschen" button (with bilingual confirm), static "Noch keine Rechnungen" empty state
  - Templates tab: all four "Vorschau" section headings and three "Zurück" buttons now carry `data-i18n`
  - Kunden/Contracts sub-tab: all vt-v form labels (Vertragsnummer, Vertragsbeginn, Vertragsende, Laufzeit/Verlängerung, Kündigungsfrist, Besondere Vereinbarungen, hint paragraph), "Vorschau" / "Vorlage drucken" buttons, "Vorlage" row-action button in contracts table
  - Admin tab: Abteilung, Bearbeiter, Kürzel, Adresse (oben links / Fußzeile), Ort (Datumszeile), Geschäftsführung, Handelsregister, "Fußzeile & Bank" stitle, info text, "Datenträger als CSV" / "Kunden als CSV" buttons, all "Zurücksetzen" / "Konfiguration speichern" buttons including SAML section
- **JS string fixes** — `renderUebergabeListe`, `formularVorschau`, `formularHerunterladen`, `rechnungVorschau`, `rechnungExportieren`, `vtVorschauUpdate`, and `tplReset` now use `t()` / `ta()` instead of hardcoded German strings
- **`applyLang()` additions** — `k-form-title`, `r-kunden_id` empty option, and `vt-v-kunden_id` empty option are now updated on language switch

---

## [1.4.2] – 2026-04-25

### Added
- **100 % DE/EN static HTML coverage** — all remaining German strings in static HTML now switch with the language toggle:
  - Dashboard KPI labels (Active Customers, Net/Year, Active Contracts, Contracts <60 Days)
  - Edit-mode banners (`Bearbeitungsmodus` / `Edit Mode`) in Tresor and Customer forms
  - All modal dialogs fully translated: DT Edit overlay, Change Password, Set Password, Edit User, New Contract, New Role
  - Admin section: New User labels, + New Role button, Support Contact card
  - Übergabe step-2 buttons (Back, Keep in Stock, Complete)
  - Templates and Admin Logo/Colour picker labels
  - Help page title, subtitle, and Contact & Support heading
  - SAML configuration hint text
  - Static footer app name now i18n-aware; version bumped to v1.4.2
- **Select option translation** — six select elements now rebuild their option text on language switch via `applyLang()`: salutation (k-anrede), contract status (k-vertragsstatus, vt-status, vt-v-status-filter), billing unit (dt-einheit, ov-dt-einheit), user status (ue-aktiv), role colour (rm-farbe)
- **JS textContent fixes** — upload zone reset messages and the "View" button in read-only customer list now use `t()` / `ta()`; Mahnung row label translated; `tresorAbbrechen()` uses translation keys

---

## [1.4.1] – 2026-04-25

### Added
- **100 % DE/EN UI coverage** — all remaining hardcoded German strings translated:
  - All `alert()` and `confirm()` messages in Auth, Customers, Media, Invoices, Handover, Safes, Admin, and tab navigation
  - All `textContent` assignments (form titles, button labels, save confirmation)
  - Table headers in Dashboard, Contracts, Safes, Users, Invoice History, and Handover Archive
  - Select options: "Select Company", "All Companies", "No Safe", "Same Company"
  - Permission/tab labels in role editor (`renderPermGrid`)
  - `dtUpdateZusammenfassung` summary labels
  - `renderArchiv` table headers and status badge
- **`ta(de, en)` helper** — thin inline function for alert/confirm/textContent strings; automatically uses active language
- **Full bilingual Help/FAQ** — all 8 categories and 26 Q&A pairs now have DE and EN versions; rendered dynamically on language switch
- **Footer version string fixed** — was hardcoded `v1.3.8`; now shows `v1.4.1` with dynamic `ta()` label

---

## [1.4.0] – 2026-04-25

### Added
- **Full DE/EN UI translation** — all dynamic render functions (`renderKunden`, `renderDT`, `renderArchiv`), form labels, sub-tab labels, step wizard labels, table headers, empty states, and button captions now switch with the 🇩🇪/🇬🇧 toggle. The `TRANS` object extended from ~50 to ~180 keys.
- **Bilingual template editor** — each of the four print templates (Übergabe, Eingang, Rechnung, Vertrag) now has a 🇩🇪/🇬🇧 toggle inside the "Texte" card. Staff can write German and English versions of introductions, body text, footers, and contract clauses independently. Print functions automatically use the language-matching template text, falling back to German if the English version is not filled in.
- **Translated Übergabe grund options** — the reason-for-handover dropdown is populated dynamically and switches with the UI language (Rueckgabe auf Wunsch / Return on Request, Vertragsende / Contract End, etc.).

---

## [1.3.9] – 2026-04-25

### Added
- **Escrow configuration at customer level** — the customer form now has a *Szenario A / Szenario B* radio toggle. In Szenario B, two new dropdowns appear: *Haupt-Eigentümer* (main owner / software developer) and *Neben-Eigentümer* (beneficiary / licensee). These are stored on the customer record (`szenario`, `escrow_haupt_id`, `escrow_neben_id` columns, auto-migrated). When creating a new media record, selecting an Auftraggeber with Szenario B pre-fills the DT form automatically.
- **Bilingual print documents** — all four document types follow the active UI language (🇩🇪 / 🇬🇧): Eingangsprotokoll / Incoming Inspection Report, Übergabeprotokoll / Handover Protocol, Einlagerungsvertrag / Storage Agreement (2-party), Dreiseitiger Einlagerungsvertrag / Three-Party Storage Agreement. Table headers, section headings, paragraph text, and signature labels are fully translated.

---

## [1.3.8] – 2026-04-25

### Added
- **DE / EN language toggle** — 🇩🇪 DE / 🇬🇧 EN button in the top bar switches the entire UI between German and English. Preference is stored in `localStorage` and survives page reloads. All static labels, tab names, status badges, section headings, button captions, and contract labels are translated. Dynamic content (rendered lists, modals) re-renders automatically on language switch via `renderAlles()`.

---

## [1.3.7] – 2026-04-25

### Added
- **2-party storage contract (Szenario A)** — "Vertrag (2 Parteien) drucken" button in Step 2 of the Übergabe form generates a print-ready storage contract between Firma 1 (operator) and the commissioning party. Sections: §1 Parties, §2 Subject & media table, §3 Return & termination, §4 Remuneration, §5 Special conditions (optional), §6 Liability. Two signature blocks.
- **3-party escrow contract (Szenario B)** — "Vertrag (3 Parteien) drucken" button generates a full software-escrow contract naming all three parties (operator, depositor / Haupt-Eigentümer, beneficiary / Neben-Eigentümer). Sections: §1–§7 covering parties, escrow purpose, release conditions, IP protection, remuneration, liability, and final provisions.
- **Freigabebedingungen / Besondere Bedingungen textarea** — free-text field below the contract buttons in Step 2. In Szenario A the label reads "Besondere Bedingungen"; in Szenario B it reads "Freigabebedingungen". Content is printed verbatim in §5 / §6 of the respective contract if filled in.
- **Contract button visibility** — "Vertrag (2 Parteien) drucken" is only shown in Szenario A; "Vertrag (3 Parteien) drucken" is only shown in Szenario B. Both are hidden in Szenario A without escrow parties.

---

## [1.3.6] – 2026-04-25

### Fixed
- **Übergabe-Archiv duplicate entry on completion** — `renderAbgeschlosseneUebergaben` now replaces an existing entry by index instead of pushing a new one, preventing a double row when the handover was already loaded at startup and then completed.

### Added
- **Eingangsprotokoll shows ownership details in Szenario B** — the print-ready incoming-inspection report now includes Haupt-Eigentümer and Auftraggeber / Neben-Eigentümer rows when the media record is configured in Szenario B (Escrow / 3-Firmen mode).
- **Rechnung per-line Eigentümer / Einlagerer** — invoice line items now include a sub-line showing the Eigentümer and Einlagerer for each DT when the record is in Szenario B.
- **"Vertrag (3 Parteien) drucken" button** — initial version of the 3-party escrow contract print function, subsequently updated in v1.3.7.

---

## [1.3.5] – 2026-04-24

### Fixed
- **Rechnung shows DTs for wrong company** — billing filter now uses `rechnungsempfaenger_id` (falling back to `kunden_id`) so each invoice only lists media records that the selected company actually pays for.
- **Completed handover appears twice in Übergabe tab** — the push after `uebergabeAbschliessen` now checks for duplicates before inserting, preventing double-display when the handover was already loaded at startup.
- **Archived DTs never appeared in Datenträger Archiv** — status string mismatch fixed: frontend sets `status='uebergeben'` (no umlaut) but the archive filter compared against `'übergeben'` (with umlaut). Both sides now use `'uebergeben'`.
- **Login completely broken after v1.3.4 deploy** — a patch was accidentally applied twice, producing a duplicate `const hatEscrow` declaration inside `dtBearbeiten`. JavaScript rejected the script entirely, causing `doLogin is not defined` and making the app unusable.
- **`ADMIN_PASSWORD` env var now synced to DB on every startup** — previously only applied on first run via `INSERT OR IGNORE`; a redeploy with `ADMIN_PASSWORD` set now always restores that password, enabling password recovery without manual DB access.

### Added
- **Szenario A / Szenario B toggle on DT form and edit overlay** — radio buttons let staff choose between *Eigene Einlagerung* (Szenario A: hides the three ownership dropdowns) and *Escrow / 3-Firmen* (Szenario B: reveals Haupt-Eigentümer, Neben-Eigentümer, Rechnungsempfänger). The toggle resets to *Eigene Einlagerung* after a new DT is saved, and auto-detects the correct mode when opening an existing DT for editing.

---

## [1.3.3] – 2026-04-24

### Added
- **3-party ownership on Datenträger level** — each media record now has three optional ownership fields:
  - **Haupt-Eigentümer** (main owner, e.g. the software developer / Firma 3)
  - **Neben-Eigentümer** (co-owner / commissioning party, e.g. Firma 2)
  - **Rechnungsempfänger** (billing recipient — whoever pays)
  - All three reference existing customer records and default to the commissioning party (Auftraggeber) when left blank.
  - Supports the full escrow scenario: Firma 2 commissions storage, Firma 3 owns the IP on the media, either may pay.

### Fixed
- **`else` branch of DT UPDATE was missing the `interne_nr` binding** — the SQL contained `interne_nr=?` but the values tuple only had `tresor_id, did`, causing a `ProgrammingError: Incorrect number of bindings` whenever a media record was updated without a new photo or scan document.
- **Duplicate `renderAbgeschlosseneUebergaben` function** — the second definition shadowed the first; only one is now present.

### Changed
- Ownership fields (Rechnungsempfänger, Eigentümer) moved from customer record to individual media record level, which matches the actual business requirement (each DT can have different owners).
- Customer form simplified: removed the kunden-level Rechnungsempfänger and Eigentümer dropdowns.

---

## [1.3.2] – 2026-04-24

### Fixed
- **`dt-interne_nr` field not visible** — patch anchor mismatch in v1.3.1 script (placeholder text differed); field now correctly added below Seriennummer.
- **Multi-company customer selects never appeared** — wrong anchor (`Anrede Ansprechpartner` vs actual `Ansprechpartner`); now correctly inserted.
- **Logo missing in Übergabe preview** — `logoData` was only populated when the Templates tab was visited; startup now also fetches the logo.
- **Duplicate HTML/JS sections** — non-idempotent v1.3.0 patch anchor caused re-insertion on each script run; duplicates removed.

---

## [1.3.1] – 2026-04-24

### Fixed
- **Duplicate route crash** — `apply_and_push_v1.3.0` used a non-idempotent patch anchor for the `DELETE /api/uebergaben/<id>` route; re-running the script inserted a second identical route definition, causing Flask to raise `AssertionError: View function mapping is overwriting an existing endpoint function: delete_uebergabe` and the server to refuse to start. The duplicate has been removed.

---

## [1.3.0] – 2026-04-24

### Added
- **Handover archive** — completed handovers are shown directly in the tab with protocol number, company, date, media count, reason, mode badge, and PDF download button
- **Delete open handovers** — 🗑 button per pending entry; removes the handover and its positions from the database
- **"Keep in stock" mode** — new button when closing a handover: marks the handover as completed but leaves the media as `stored` (useful when a customer temporarily takes media but keeps paying)
- **Optional document upload** — a handover can now be closed without an uploaded document; a confirmation dialog is shown instead of a hard block
- **Internal number for media** — free-text `Internal No.` field when creating or editing a media record; visible in the list and included in CSV export
- **Multi-company logic** — optional billing recipient (Firma B pays for Firma A) and media owner selectable per customer record
- **Help tab full width** — removed the `max-width: 860px` constraint so the content fills the available space
- **Mobile view improvements** — tab bar scrolls horizontally without wrapping; tables are horizontally scrollable on small screens; more compact padding below 600 px

### Fixed
- **Handover recipient bug** — the recipient field was sent with the wrong JS key (`Empfänger` instead of `empfaenger`) and was always empty in the database; fixed on both client and server
- **DB migrations** — new columns (`weiter_im_bestand`, `interne_nr`, `rechnungsempfaenger_id`, `eigentuemer_id`) are added automatically on the next container start without manual schema changes

### Changed
- Closing a handover without a document now shows a confirmation dialog instead of blocking the action entirely
- Completed handovers appear in the archive immediately without a page reload

---

## [1.2.0] – 2026-04-20

### Added
- Media archive as a sub-tab (Media → Record / Archive)
- Customers & Contracts combined as one tab with sub-navigation
- Invoices & History combined as one tab with sub-navigation
- Safe detail view accessible by clicking the safe name
- Salutation field (Mr / Ms / Dr / Prof / Other) for contact persons
- Company data moved to the Admin section instead of the Templates section
- PDF button per invoice in the invoice history
- Reminder function per invoice in the invoice history with print button

### Fixed
- Safe dropdown was empty when editing a media record
- Handover completion after document download threw an error
- Removed outdated tab permissions from role management
- Responsive design: tab bar was wrapping instead of scrolling

---

## [1.1.1] – 2026-04-20

### Added
- Safe tab permission: roles can show/hide the Safes tab
- Responsive layout improvements for tablet and mobile

### Fixed
- Saving or deleting a safe triggered an unintended logout (`localStorage` vs `sessionStorage` mismatch)

---

## [1.1.0] – 2026-04-20

### Added
- Safe management (🔒 Safes) — full CRUD with location, purchase data, maintenance dates, and maintenance contract upload
- Safe assignment when registering a media record
- Dashboard: maintenance warnings for safes (60-day preview)
- CSV export extended with safe location columns
- Optional SQLite encryption via `DB_KEY` environment variable (SQLCipher AES-256)

### Changed
- Contact email updated: `marcel.capelan@tuv.com` → `info@capelan.de`

---

## [1.0.0] – 2025-04-19

### Initial public release

- Dashboard with KPIs, contract expiry warnings, and maintenance notices
- Customer management with contracts, volume discounts, and contract history
- Media management: registration, photos, incoming inspection report
- Handover workflow with print-ready handover protocol
- Invoice generation with discount tiers, VAT, and reminder function
- Archive of all returned media
- Letter template editor (invoice, handover, incoming, contract)
- Admin panel: user management, roles & permissions
- SAML 2.0 / SSO (Azure AD, Okta, Keycloak)
- PBKDF2 password security, token-based sessions, Docker Swarm support

---

*© 2025 Marcel Capelan — [capelan.de](https://capelan.de)*
