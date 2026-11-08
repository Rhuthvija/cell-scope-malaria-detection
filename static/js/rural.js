/* ==========================================================================
   CELL SCOPE — Rural health features
   - English / Telugu / Hindi interface for ASHA workers
   - Village, district, health worker and GPS capture
   - Image compression before upload (works on slow 2G/3G links)
   - "What to do next" guidance, WhatsApp referral sharing, 108 ambulance link
   - Outbreak map (village hotspots) and referral list
   - Offline app shell (service worker)
   Loaded after app.js; app.js calls appendRuralFields, compressForUpload,
   showRuralResult and loadOutbreaks if they exist.
   ========================================================================== */

/* ---------------------------------------------------------------- i18n --- */
const I18N = {
  en: {
    nav_home: 'Home', nav_diagnosis: 'Diagnosis', nav_tracking: 'Patient Records', nav_analytics: 'Analytics',
    nav_outbreaks: 'Outbreak Map', hero_cta: 'Run Diagnosis Test',
    patient_card: '👤 Patient Details Registration', lbl_name: 'Patient Name *', lbl_id: 'Patient ID / MRN',
    lbl_age: 'Age *', lbl_gender: 'Gender', lbl_phone: 'Phone Number', lbl_village: 'Village', lbl_district: 'District',
    lbl_worker: 'ASHA / Health Worker', lbl_location: 'GPS Location (optional)', btn_location: '📍 Use My Location',
    upload_card: '🔬 Blood Cell Image Upload', next_steps: 'What To Do Next', refer_banner: 'Refer to Doctor / PHC',
    btn_whatsapp: 'Share on WhatsApp', btn_call108: '📞 Call 108 Ambulance',
    disclaimer: 'Screening only — not a final diagnosis. Confirm with an RDT or a trained microscopist.',
    outbreak_title: '🗺️ Malaria Outbreak Map',
    outbreak_sub: 'Village-level positive cases. A village is flagged as a hotspot when it has 3 or more positive tests in the selected period.',
    stat_tests: 'Tests', stat_pos: 'Positive', stat_hot: 'Hotspot Villages', stat_ref: 'Referrals',
    map_offline: 'Map needs internet. The village table below still works offline.',
    th_village: 'Village', th_district: 'District', th_tests: 'Tests', th_pos: 'Positive', th_positivity: 'Positivity',
    th_last: 'Last Test', th_status: 'Status', th_date: 'Date', th_patient: 'Patient', th_age: 'Age', th_risk: 'Risk',
    th_worker: 'Health Worker', ref_title: '🚑 Patients To Refer', days: 'Last {n} days',
    status_hot: 'Hotspot', status_watch: 'Watch', status_ok: 'Normal', no_refs: 'No referrals in this period.',
    no_data: 'No tests recorded in this period.', loc_getting: 'Getting location…', loc_ok: 'Location saved ✓',
    loc_fail: 'Location not available — type the village name instead.',
    smear_title: '🔴 Detected Cells (red box = infected)', smear_badge: 'Cell-by-cell analysis',
    band_clear: 'Negative', band_low: 'Low risk', band_moderate: 'Moderate risk', band_high: 'High risk', band_critical: 'Critical risk',
    steps_clear: ['No malaria parasites seen.', 'If fever continues, test again after 24 hours or do an RDT.', 'Use mosquito nets and remove standing water near the house.'],
    steps_low: ['Probably no malaria, but the result is uncertain.', 'Confirm with an RDT if the patient has fever.', 'Re-test if fever continues.'],
    steps_moderate: ['Possible malaria infection.', 'Confirm today with an RDT or a trained microscopist.', 'If confirmed, start treatment through the ASHA / PHC as per national guidelines.'],
    steps_high: ['Malaria parasites detected.', 'Confirm with an RDT and start treatment today through the PHC.', 'Refer to a doctor and share this result with the PHC.'],
    steps_critical: ['High parasite load — this is an emergency.', 'Take the patient to the PHC / hospital immediately. Call 108 for an ambulance.', 'Watch for danger signs: confusion, fits, unable to drink, repeated vomiting, dark urine.'],
    wa_header: 'CELL SCOPE malaria screening', wa_patient: 'Patient', wa_village: 'Village', wa_result: 'Result',
    wa_parasitemia: 'Parasitemia', wa_date: 'Date', wa_worker: 'Health worker', wa_action: 'Action',
    wa_footer: 'Screening only — please confirm with RDT / microscopy.',
    res_parasitized: 'Malaria parasites detected', res_uninfected: 'No parasites detected'
  },
  te: {
    nav_home: 'హోమ్', nav_diagnosis: 'పరీక్ష', nav_tracking: 'రోగుల రికార్డులు', nav_analytics: 'విశ్లేషణ',
    nav_outbreaks: 'వ్యాప్తి మ్యాప్', hero_cta: 'పరీక్ష ప్రారంభించండి',
    patient_card: '👤 రోగి వివరాల నమోదు', lbl_name: 'రోగి పేరు *', lbl_id: 'రోగి ID',
    lbl_age: 'వయస్సు *', lbl_gender: 'లింగం', lbl_phone: 'ఫోన్ నంబర్', lbl_village: 'గ్రామం', lbl_district: 'జిల్లా',
    lbl_worker: 'ఆశా / ఆరోగ్య కార్యకర్త', lbl_location: 'GPS లొకేషన్ (ఐచ్ఛికం)', btn_location: '📍 నా లొకేషన్ వాడండి',
    upload_card: '🔬 రక్త కణ చిత్రం అప్‌లోడ్', next_steps: 'తరువాత ఏమి చేయాలి', refer_banner: 'డాక్టర్ / PHC కి పంపండి',
    btn_whatsapp: 'వాట్సాప్‌లో పంపండి', btn_call108: '📞 108 అంబులెన్స్‌కు కాల్ చేయండి',
    disclaimer: 'ఇది స్క్రీనింగ్ మాత్రమే — తుది నిర్ధారణ కాదు. RDT లేదా శిక్షణ పొందిన మైక్రోస్కోపిస్ట్‌తో నిర్ధారించండి.',
    outbreak_title: '🗺️ మలేరియా వ్యాప్తి మ్యాప్',
    outbreak_sub: 'గ్రామాల వారీగా పాజిటివ్ కేసులు. ఎంచుకున్న కాలంలో 3 లేదా అంతకంటే ఎక్కువ పాజిటివ్ పరీక్షలు ఉన్న గ్రామం హాట్‌స్పాట్‌గా గుర్తించబడుతుంది.',
    stat_tests: 'పరీక్షలు', stat_pos: 'పాజిటివ్', stat_hot: 'హాట్‌స్పాట్ గ్రామాలు', stat_ref: 'రిఫరల్స్',
    map_offline: 'మ్యాప్‌కు ఇంటర్నెట్ అవసరం. కింది గ్రామ పట్టిక ఆఫ్‌లైన్‌లో కూడా పనిచేస్తుంది.',
    th_village: 'గ్రామం', th_district: 'జిల్లా', th_tests: 'పరీక్షలు', th_pos: 'పాజిటివ్', th_positivity: 'పాజిటివిటీ',
    th_last: 'చివరి పరీక్ష', th_status: 'స్థితి', th_date: 'తేదీ', th_patient: 'రోగి', th_age: 'వయస్సు', th_risk: 'ప్రమాదం',
    th_worker: 'ఆరోగ్య కార్యకర్త', ref_title: '🚑 రిఫర్ చేయాల్సిన రోగులు', days: 'గత {n} రోజులు',
    status_hot: 'హాట్‌స్పాట్', status_watch: 'గమనించండి', status_ok: 'సాధారణం', no_refs: 'ఈ కాలంలో రిఫరల్స్ లేవు.',
    no_data: 'ఈ కాలంలో పరీక్షలు నమోదు కాలేదు.', loc_getting: 'లొకేషన్ తీసుకుంటోంది…', loc_ok: 'లొకేషన్ సేవ్ అయింది ✓',
    loc_fail: 'లొకేషన్ అందుబాటులో లేదు — గ్రామం పేరు టైప్ చేయండి.',
    smear_title: '🔴 గుర్తించిన కణాలు (ఎరుపు పెట్టె = సోకినవి)', smear_badge: 'కణాల వారీ విశ్లేషణ',
    band_clear: 'నెగటివ్', band_low: 'తక్కువ ప్రమాదం', band_moderate: 'మధ్యస్థ ప్రమాదం', band_high: 'అధిక ప్రమాదం', band_critical: 'తీవ్ర ప్రమాదం',
    steps_clear: ['మలేరియా పరాన్నజీవులు కనిపించలేదు.', 'జ్వరం తగ్గకపోతే 24 గంటల తర్వాత మళ్ళీ పరీక్ష చేయండి లేదా RDT చేయండి.', 'దోమతెరలు వాడండి, ఇంటి దగ్గర నిల్వ నీరు లేకుండా చూడండి.'],
    steps_low: ['మలేరియా లేకపోవచ్చు, కానీ ఫలితం ఖచ్చితంగా లేదు.', 'జ్వరం ఉంటే RDT తో నిర్ధారించండి.', 'జ్వరం కొనసాగితే మళ్ళీ పరీక్ష చేయండి.'],
    steps_moderate: ['మలేరియా సోకే అవకాశం ఉంది.', 'ఈరోజే RDT లేదా శిక్షణ పొందిన మైక్రోస్కోపిస్ట్ ద్వారా నిర్ధారించండి.', 'నిర్ధారణ అయితే జాతీయ మార్గదర్శకాల ప్రకారం ఆశా / PHC ద్వారా చికిత్స ప్రారంభించండి.'],
    steps_high: ['మలేరియా పరాన్నజీవులు కనుగొనబడ్డాయి.', 'RDT తో నిర్ధారించి, ఈరోజే PHC ద్వారా చికిత్స ప్రారంభించండి.', 'డాక్టర్ వద్దకు పంపండి, ఈ ఫలితాన్ని PHC కి పంపండి.'],
    steps_critical: ['పరాన్నజీవుల సంఖ్య ఎక్కువగా ఉంది — ఇది అత్యవసర పరిస్థితి.', 'రోగిని వెంటనే PHC / ఆసుపత్రికి తీసుకెళ్లండి. అంబులెన్స్ కోసం 108 కి కాల్ చేయండి.', 'ప్రమాద సంకేతాలు గమనించండి: అయోమయం, ఫిట్స్, తాగలేకపోవడం, పదే పదే వాంతులు, ముదురు రంగు మూత్రం.'],
    wa_header: 'CELL SCOPE మలేరియా స్క్రీనింగ్', wa_patient: 'రోగి', wa_village: 'గ్రామం', wa_result: 'ఫలితం',
    wa_parasitemia: 'పరాన్నజీవుల శాతం', wa_date: 'తేదీ', wa_worker: 'ఆరోగ్య కార్యకర్త', wa_action: 'చర్య',
    wa_footer: 'ఇది స్క్రీనింగ్ మాత్రమే — దయచేసి RDT / మైక్రోస్కోపీతో నిర్ధారించండి.',
    res_parasitized: 'మలేరియా పరాన్నజీవులు కనుగొనబడ్డాయి', res_uninfected: 'పరాన్నజీవులు కనిపించలేదు'
  },
  hi: {
    nav_home: 'होम', nav_diagnosis: 'जाँच', nav_tracking: 'मरीज़ रिकॉर्ड', nav_analytics: 'विश्लेषण',
    nav_outbreaks: 'प्रकोप मानचित्र', hero_cta: 'जाँच शुरू करें',
    patient_card: '👤 मरीज़ का पंजीकरण', lbl_name: 'मरीज़ का नाम *', lbl_id: 'मरीज़ ID',
    lbl_age: 'उम्र *', lbl_gender: 'लिंग', lbl_phone: 'फ़ोन नंबर', lbl_village: 'गाँव', lbl_district: 'ज़िला',
    lbl_worker: 'आशा / स्वास्थ्य कार्यकर्ता', lbl_location: 'GPS लोकेशन (वैकल्पिक)', btn_location: '📍 मेरी लोकेशन लें',
    upload_card: '🔬 रक्त कोशिका फ़ोटो अपलोड', next_steps: 'आगे क्या करें', refer_banner: 'डॉक्टर / PHC को रेफ़र करें',
    btn_whatsapp: 'व्हाट्सएप पर भेजें', btn_call108: '📞 108 एम्बुलेंस को कॉल करें',
    disclaimer: 'यह केवल स्क्रीनिंग है — अंतिम निदान नहीं। RDT या प्रशिक्षित माइक्रोस्कोपिस्ट से पुष्टि करें।',
    outbreak_title: '🗺️ मलेरिया प्रकोप मानचित्र',
    outbreak_sub: 'गाँव-वार पॉज़िटिव केस। चुनी गई अवधि में 3 या ज़्यादा पॉज़िटिव जाँच वाले गाँव को हॉटस्पॉट माना जाता है।',
    stat_tests: 'जाँचें', stat_pos: 'पॉज़िटिव', stat_hot: 'हॉटस्पॉट गाँव', stat_ref: 'रेफ़रल',
    map_offline: 'मानचित्र के लिए इंटरनेट चाहिए। नीचे की गाँव तालिका ऑफ़लाइन भी काम करती है।',
    th_village: 'गाँव', th_district: 'ज़िला', th_tests: 'जाँचें', th_pos: 'पॉज़िटिव', th_positivity: 'पॉज़िटिविटी',
    th_last: 'आखिरी जाँच', th_status: 'स्थिति', th_date: 'तारीख', th_patient: 'मरीज़', th_age: 'उम्र', th_risk: 'जोखिम',
    th_worker: 'स्वास्थ्य कार्यकर्ता', ref_title: '🚑 रेफ़र किए जाने वाले मरीज़', days: 'पिछले {n} दिन',
    status_hot: 'हॉटस्पॉट', status_watch: 'निगरानी', status_ok: 'सामान्य', no_refs: 'इस अवधि में कोई रेफ़रल नहीं।',
    no_data: 'इस अवधि में कोई जाँच दर्ज नहीं।', loc_getting: 'लोकेशन ली जा रही है…', loc_ok: 'लोकेशन सेव हो गई ✓',
    loc_fail: 'लोकेशन उपलब्ध नहीं — गाँव का नाम लिखें।',
    smear_title: '🔴 पहचानी गई कोशिकाएँ (लाल बॉक्स = संक्रमित)', smear_badge: 'कोशिका-वार विश्लेषण',
    band_clear: 'नेगेटिव', band_low: 'कम जोखिम', band_moderate: 'मध्यम जोखिम', band_high: 'उच्च जोखिम', band_critical: 'गंभीर जोखिम',
    steps_clear: ['मलेरिया परजीवी नहीं मिले।', 'बुखार बना रहे तो 24 घंटे बाद फिर जाँच करें या RDT करें।', 'मच्छरदानी का उपयोग करें और घर के पास जमा पानी हटाएँ।'],
    steps_low: ['शायद मलेरिया नहीं है, पर परिणाम पक्का नहीं है।', 'बुखार हो तो RDT से पुष्टि करें।', 'बुखार बना रहे तो दोबारा जाँच करें।'],
    steps_moderate: ['मलेरिया संक्रमण की संभावना है।', 'आज ही RDT या प्रशिक्षित माइक्रोस्कोपिस्ट से पुष्टि करें।', 'पुष्टि होने पर राष्ट्रीय दिशानिर्देशों के अनुसार आशा / PHC से इलाज शुरू करें।'],
    steps_high: ['मलेरिया परजीवी मिले हैं।', 'RDT से पुष्टि करें और आज ही PHC से इलाज शुरू करें।', 'डॉक्टर के पास भेजें और यह परिणाम PHC को भेजें।'],
    steps_critical: ['परजीवी की मात्रा बहुत ज़्यादा है — यह आपातकाल है।', 'मरीज़ को तुरंत PHC / अस्पताल ले जाएँ। एम्बुलेंस के लिए 108 पर कॉल करें।', 'खतरे के लक्षण देखें: भ्रम, दौरे, पी न पाना, बार-बार उल्टी, गहरे रंग का पेशाब।'],
    wa_header: 'CELL SCOPE मलेरिया स्क्रीनिंग', wa_patient: 'मरीज़', wa_village: 'गाँव', wa_result: 'परिणाम',
    wa_parasitemia: 'परजीवी प्रतिशत', wa_date: 'तारीख', wa_worker: 'स्वास्थ्य कार्यकर्ता', wa_action: 'कार्रवाई',
    wa_footer: 'यह केवल स्क्रीनिंग है — कृपया RDT / माइक्रोस्कोपी से पुष्टि करें।',
    res_parasitized: 'मलेरिया परजीवी मिले', res_uninfected: 'परजीवी नहीं मिले'
  }
};

let currentLang = 'en';
let lastRuralData = null;

function t(key) {
  return (I18N[currentLang] && I18N[currentLang][key] !== undefined) ? I18N[currentLang][key] : I18N.en[key];
}

function setLanguage(lang) {
  currentLang = I18N[lang] ? lang : 'en';
  try { localStorage.setItem('cellscope_lang', currentLang); } catch (e) { /* storage unavailable */ }
  document.documentElement.lang = currentLang;
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const val = t(el.getAttribute('data-i18n'));
    if (typeof val === 'string') el.textContent = val;
  });
  document.querySelectorAll('[data-i18n-days]').forEach((el) => {
    el.textContent = t('days').replace('{n}', el.getAttribute('data-i18n-days'));
  });
  const sel = document.getElementById('lang-select');
  if (sel && sel.value !== currentLang) sel.value = currentLang;
  if (lastRuralData) showRuralResult(lastRuralData);
  if (document.getElementById('page-outbreaks')?.style.display === 'block') loadOutbreaks();
}

/* ------------------------------------------------------------ location --- */
let ruralCoords = null;

function captureLocation() {
  const status = document.getElementById('rural-loc-status');
  if (!navigator.geolocation) { if (status) status.textContent = t('loc_fail'); return; }
  if (status) status.textContent = t('loc_getting');
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      ruralCoords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      if (status) status.textContent = `${t('loc_ok')} (${ruralCoords.lat.toFixed(4)}, ${ruralCoords.lon.toFixed(4)})`;
    },
    () => { ruralCoords = null; if (status) status.textContent = t('loc_fail'); },
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 }
  );
}

function appendRuralFields(formData) {
  const val = (id) => (document.getElementById(id)?.value || '').trim();
  formData.append('village', val('rural-village'));
  formData.append('district', val('rural-district'));
  formData.append('health_worker', val('rural-worker'));
  if (ruralCoords) {
    formData.append('latitude', String(ruralCoords.lat));
    formData.append('longitude', String(ruralCoords.lon));
  }
  // Remember village / district / worker between patients: an ASHA worker
  // usually tests many people in the same village in one session.
  try {
    localStorage.setItem('cellscope_rural', JSON.stringify({
      village: val('rural-village'), district: val('rural-district'), worker: val('rural-worker')
    }));
  } catch (e) { /* storage unavailable */ }
}

/* ------------------------------------------------- upload compression --- */
// Phone photos are often 3-8 MB. On a 2G/3G link that can take minutes, so
// large images are resized in the browser first. Smears keep enough resolution
// for cell detection (2000 px long side); single cells only need ~600 px.
async function compressForUpload(file, mode) {
  try {
    if (!file || !file.type || !file.type.startsWith('image/')) return file;
    const maxSide = (mode === 'smear') ? 2000 : 600;
    const bitmap = await loadBitmap(file);
    const w = bitmap.width, h = bitmap.height;
    const scale = Math.min(1, maxSide / Math.max(w, h));
    if (scale === 1 && file.size <= 1.5 * 1024 * 1024) return file;   // already small
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', 0.92));
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], (file.name || 'image').replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' });
  } catch (e) {
    console.warn('Compression skipped:', e);
    return file;
  }
}

function loadBitmap(file) {
  if (window.createImageBitmap) return createImageBitmap(file);
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

/* ------------------------------------------- next steps + WhatsApp + 108 --- */
function showRuralResult(data) {
  lastRuralData = data;
  const diag = data.diagnosis || {};
  const patient = data.patient || {};
  const box = document.getElementById('rural-next');
  if (!box) return;
  const band = diag.band || 'clear';

  const list = document.getElementById('rural-next-list');
  list.innerHTML = '';
  (t('steps_' + band) || []).forEach((step) => {
    const li = document.createElement('li');
    li.textContent = step;
    list.appendChild(li);
  });

  document.getElementById('rural-refer-badge').style.display = diag.refer ? 'inline-block' : 'none';
  document.getElementById('rural-108-btn').style.display = (band === 'critical') ? 'inline-flex' : 'none';

  const result = diag.label === 'Parasitized' ? t('res_parasitized') : t('res_uninfected');
  const lines = [
    `*${t('wa_header')}*`,
    `${t('wa_patient')}: ${patient.name || ''}${patient.age ? ' (' + patient.age + ')' : ''}`,
    diag.village ? `${t('wa_village')}: ${diag.village}${diag.district ? ', ' + diag.district : ''}` : null,
    `${t('wa_result')}: ${result} — ${t('band_' + band)}`,
    (diag.parasitemia_pct !== null && diag.parasitemia_pct !== undefined) ? `${t('wa_parasitemia')}: ${diag.parasitemia_pct}%` : null,
    `${t('wa_date')}: ${diag.date || ''}`,
    diag.health_worker ? `${t('wa_worker')}: ${diag.health_worker}` : null,
    `${t('wa_action')}: ${(t('steps_' + band) || [])[1] || ''}`,
    `_${t('wa_footer')}_`
  ].filter(Boolean);
  document.getElementById('rural-wa-btn').href = 'https://wa.me/?text=' + encodeURIComponent(lines.join('\n'));

  // Full smear: the second image is the smear with infected cells boxed.
  const gradImg = document.getElementById('res-gradcam-img');
  const card = gradImg ? gradImg.closest('.image-card') : null;
  if (card) {
    const title = card.querySelector('.image-card-title');
    const badge = card.querySelector('.badge-gradcam');
    if (!card.dataset.origTitle && title) card.dataset.origTitle = title.textContent;
    if (!card.dataset.origBadge && badge) card.dataset.origBadge = badge.textContent;
    const isSmear = diag.mode === 'smear';
    if (title) title.textContent = isSmear ? t('smear_title') : card.dataset.origTitle;
    if (badge) badge.textContent = isSmear ? t('smear_badge') : card.dataset.origBadge;
    const legend = card.querySelector('.gradcam-legend');
    if (legend) legend.style.display = isSmear ? 'none' : '';
    const footer = card.querySelector('.image-card-footer span');
    if (footer && !card.dataset.origFooter) card.dataset.origFooter = footer.textContent;
    if (footer) footer.textContent = isSmear && diag.smear
      ? `${diag.smear.cells_detected} cells analysed · ${diag.smear.cells_parasitized} infected`
      : card.dataset.origFooter;
  }

  box.style.display = 'block';
}

/* --------------------------------------------------------- outbreak map --- */
let outbreakMap = null;
let outbreakLayer = null;

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function loadOutbreaks() {
  const days = document.getElementById('outbreak-days')?.value || 14;
  try {
    const [obRes, refRes] = await Promise.all([
      fetch(`/api/outbreaks?days=${days}`), fetch(`/api/referrals?days=${Math.max(days, 7)}`)
    ]);
    const ob = await obRes.json();
    const refs = await refRes.json();
    document.getElementById('ob-tests').textContent = ob.total_tests;
    document.getElementById('ob-pos').textContent = ob.total_positives;
    document.getElementById('ob-hot').textContent = ob.hotspots.length;
    document.getElementById('ob-ref').textContent = refs.length;
    renderOutbreakTable(ob.villages);
    renderReferralTable(refs);
    renderOutbreakMap(ob.villages);
  } catch (e) {
    console.error('Outbreak data failed to load:', e);
  }
}

function villageStatus(v) {
  if (v.hotspot) return { label: t('status_hot'), color: 'var(--c-red)' };
  if (v.positives > 0) return { label: t('status_watch'), color: 'var(--c-orange)' };
  return { label: t('status_ok'), color: 'var(--c-green-light)' };
}

function renderOutbreakTable(villages) {
  const tbody = document.getElementById('outbreak-tbody');
  if (!villages.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="color: var(--text-muted);">${escapeHtml(t('no_data'))}</td></tr>`;
    return;
  }
  tbody.innerHTML = villages.map((v) => {
    const st = villageStatus(v);
    return `<tr>
      <td><strong>${escapeHtml(v.village)}</strong></td>
      <td>${escapeHtml(v.district)}</td>
      <td>${v.tests}</td>
      <td style="color: var(--c-pink-light); font-weight: 700;">${v.positives}</td>
      <td>${v.positivity_pct}%</td>
      <td>${escapeHtml(v.last_test)}</td>
      <td><span style="color: ${st.color}; font-weight: 700;">● ${escapeHtml(st.label)}</span></td>
    </tr>`;
  }).join('');
}

function renderReferralTable(refs) {
  const tbody = document.getElementById('referral-tbody');
  if (!refs.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="color: var(--text-muted);">${escapeHtml(t('no_refs'))}</td></tr>`;
    return;
  }
  tbody.innerHTML = refs.map((r) => {
    const crit = (r.risk_band || '').toLowerCase().startsWith('critical');
    return `<tr>
      <td>${escapeHtml(r.visit_date)}</td>
      <td><strong>${escapeHtml(r.name)}</strong> <span style="color: var(--text-muted);">${escapeHtml(r.patient_code)}</span></td>
      <td>${escapeHtml(r.age)}</td>
      <td>${escapeHtml(r.village || '—')}</td>
      <td style="color: ${crit ? 'var(--c-red)' : 'var(--c-orange)'}; font-weight: 700;">${escapeHtml(r.risk_band)}</td>
      <td>${escapeHtml(r.health_worker || '—')}</td>
    </tr>`;
  }).join('');
}

function renderOutbreakMap(villages) {
  const mapEl = document.getElementById('outbreak-map');
  const note = document.getElementById('outbreak-map-note');
  if (!window.L) {                       // Leaflet didn't load: offline or blocked
    mapEl.style.display = 'none';
    note.style.display = 'block';
    return;
  }
  mapEl.style.display = 'block';
  note.style.display = 'none';
  if (!outbreakMap) {
    outbreakMap = L.map(mapEl, { scrollWheelZoom: false }).setView([18.2, 80.3], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18, attribution: '&copy; OpenStreetMap contributors'
    }).addTo(outbreakMap);
    outbreakLayer = L.layerGroup().addTo(outbreakMap);
  }
  outbreakLayer.clearLayers();
  const pts = [];
  villages.filter((v) => v.lat !== null && v.lon !== null).forEach((v) => {
    const color = v.hotspot ? '#ef4444' : (v.positives > 0 ? '#f97316' : '#10b981');
    const radius = 8 + Math.min(22, v.positives * 4);
    L.circleMarker([v.lat, v.lon], { radius, color, fillColor: color, fillOpacity: 0.45, weight: 2 })
      .bindPopup(`<strong>${escapeHtml(v.village)}</strong><br>${escapeHtml(v.district)}<br>` +
                 `${escapeHtml(t('th_tests'))}: ${v.tests} · ${escapeHtml(t('th_pos'))}: ${v.positives} (${v.positivity_pct}%)`)
      .addTo(outbreakLayer);
    pts.push([v.lat, v.lon]);
  });
  setTimeout(() => {
    outbreakMap.invalidateSize();
    if (pts.length) outbreakMap.fitBounds(pts, { padding: [40, 40], maxZoom: 10 });
  }, 150);
}

/* ------------------------------------------------------------- startup --- */
document.addEventListener('DOMContentLoaded', () => {
  try {
    const saved = JSON.parse(localStorage.getItem('cellscope_rural') || '{}');
    if (saved.village) document.getElementById('rural-village').value = saved.village;
    if (saved.district) document.getElementById('rural-district').value = saved.district;
    if (saved.worker) document.getElementById('rural-worker').value = saved.worker;
  } catch (e) { /* storage unavailable */ }

  let lang = 'en';
  try { lang = localStorage.getItem('cellscope_lang') || 'en'; } catch (e) { /* ignore */ }
  if (lang !== 'en') setLanguage(lang);

  // Offline app shell: pages and scripts load even with no signal.
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch((e) => console.warn('Service worker not registered:', e));
  }
});
