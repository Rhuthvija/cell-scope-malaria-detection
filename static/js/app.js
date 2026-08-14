/* ==========================================================================
   CELL SCOPE — Master Application Module
   - Glossy 3D Cellular Hero Canvas
   - Upload Dropzone & Confirmation Preview Card State
   - Multi-stage MobileNet Inference Pipeline & Progress Overlay
   - Grad-CAM Explainability Heatmap & Side-by-Side Results Display
   - Semi-Circular Risk Meter with Dynamic Taglines
   - Database Multi-Visit Persistence & Patient Records
   - Redesigned Patient-Centric & Global Population Analytics
   ========================================================================== */

let activeTab = 'home';
let currentUploadMode = 'single';
let currentFile = null;
let activePatientId = 1;
let currentDiagnosisData = null;
let currentVisitId = null;
let currentModalVisitId = null;
let isPatientSavedForSession = false;
let heroAnimationController = null;

let scatterAgeChartInstance = null;
let timeSeriesChartInstance = null;
let ratioChartInstance = null;
let patientTrendChartInstance = null;

document.addEventListener('DOMContentLoaded', () => {
  initGlossy3DCellularCanvas();
  initDragAndDrop();
  initPatientFormValidation();
  loadPatientRecordsFromDB();
  loadAnalyticsFromDB();
  checkPatientAutoAccess();
});

/* --------------------------------------------------------------------------
   1. Abstract Glossy 3D Cellular Animation
   -------------------------------------------------------------------------- */
function initGlossy3DCellularCanvas() {
  const canvas = document.getElementById('cellular-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const hero = document.getElementById('page-home');
  let width = 0;
  let height = 0;
  let time = 0;
  let animationFrameId = null;
  let isRunning = false;

  // Deliberately designed, percentage-based anchors.  Keeping these immutable
  // prevents a new, random layout or accumulated drift when Home is revisited.
  const cells = [
    { x: 0.50, y: 0.45, r: 130, color1: '#ec4899', color2: '#7c3aed', color3: '#06b6d4', phase: 0.0 },
    { x: 0.32, y: 0.65, r: 90, color1: '#2563eb', color2: '#06b6d4', color3: '#8b5cf6', phase: 1.2 },
    { x: 0.68, y: 0.31, r: 100, color1: '#8b5cf6', color2: '#ec4899', color3: '#2563eb', phase: 2.4 },
    { x: 0.14, y: 0.28, r: 70, color1: '#06b6d4', color2: '#3b82f6', color3: '#10b981', phase: 3.6 },
    { x: 0.86, y: 0.68, r: 75, color1: '#f43f5e', color2: '#7c3aed', color3: '#ddd6fe', phase: 4.8 },
  ];

  function resizeCanvas() {
    const bounds = hero ? hero.getBoundingClientRect() : canvas.getBoundingClientRect();
    width = Math.max(1, Math.round(bounds.width || window.innerWidth));
    height = Math.max(1, Math.round(bounds.height || window.innerHeight));
    canvas.width = width;
    canvas.height = height;
  }

  function renderAbstractCells(advance = true) {
    if (advance) time += 0.012;
    ctx.clearRect(0, 0, width, height);

    const bgGlow = ctx.createRadialGradient(
      width / 2, height / 2, 80,
      width / 2, height / 2, Math.max(width, height) * 0.65
    );
    bgGlow.addColorStop(0, 'rgba(124, 58, 237, 0.15)');
    bgGlow.addColorStop(0.5, 'rgba(6, 182, 212, 0.08)');
    bgGlow.addColorStop(1, 'rgba(9, 13, 22, 0.95)');
    ctx.fillStyle = bgGlow;
    ctx.fillRect(0, 0, width, height);

    cells.forEach((c) => {
      // Positions are recalculated from immutable anchors on each frame rather
      // than incremented, so they can never wander or wrap off the viewport.
      const x = width * c.x + Math.sin(time + c.phase) * 8;
      const y = height * c.y + Math.cos(time * 0.8 + c.phase) * 6;
      const offsetR = c.r + Math.sin(time * 1.5 + c.phase) * 5;

      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, offsetR, 0, Math.PI * 2);

      const grad = ctx.createRadialGradient(
        x - offsetR * 0.35,
        y - offsetR * 0.35,
        offsetR * 0.1,
        x,
        y,
        offsetR
      );
      grad.addColorStop(0, 'rgba(255, 255, 255, 0.65)');
      grad.addColorStop(0.3, c.color1);
      grad.addColorStop(0.7, c.color2);
      grad.addColorStop(1, c.color3);

      ctx.fillStyle = grad;
      ctx.shadowColor = c.color1;
      ctx.shadowBlur = 40;
      ctx.fill();

      ctx.lineWidth = 2;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
      ctx.stroke();

      ctx.restore();
    });

    if (isRunning) animationFrameId = requestAnimationFrame(renderAbstractCells);
  }

  function start({ reset = false } = {}) {
    if (isRunning) return;
    if (reset) time = 0;
    resizeCanvas();
    isRunning = true;
    renderAbstractCells(false);
  }

  function stop() {
    isRunning = false;
    if (animationFrameId !== null) cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }

  window.addEventListener('resize', () => {
    if (!isRunning) return;
    resizeCanvas();
    renderAbstractCells(false);
  });

  heroAnimationController = { start, stop };
  start({ reset: true });
}

/* --------------------------------------------------------------------------
   2. Clean Navigation Switcher
   -------------------------------------------------------------------------- */
function switchTab(tabId) {
  if (tabId !== 'home') {
    heroAnimationController?.stop();
  }
  activeTab = tabId;

  const navItems = ['home', 'diagnosis', 'tracking', 'analytics'];
  navItems.forEach((item) => {
    const navEl = document.getElementById(`nav-${item}`);
    const pageEl = document.getElementById(`page-${item}`);
    if (navEl) navEl.classList.remove('active');
    if (pageEl) pageEl.style.display = 'none';
  });

  const activeNav = document.getElementById(`nav-${tabId}`);
  const activePage = document.getElementById(`page-${tabId}`);
  if (activeNav) activeNav.classList.add('active');
  // Home is a flex-based hero. Restoring it as block after a tab switch
  // overrides `.hero-section { display: flex }` and shifts the title/orbs out
  // of their designed centered composition.
  if (activePage) activePage.style.display = (tabId === 'home') ? 'flex' : 'block';

  // A hidden canvas must not keep an RAF loop alive. Restarting after the
  // section becomes visible resets it to the same designed opening layout.
  if (tabId === 'home') heroAnimationController?.start({ reset: true });

  window.scrollTo({ top: 0, behavior: 'smooth' });

  if (tabId === 'tracking') loadPatientRecordsFromDB();
  if (tabId === 'analytics') loadAnalyticsFromDB();
}

/* --------------------------------------------------------------------------
   3. Patient Registration, Form Validation & Explicit DB Save
   -------------------------------------------------------------------------- */
function initPatientFormValidation() {
  const nameInput = document.getElementById('patient-name-input');
  const ageInput = document.getElementById('patient-age');
  const genderSelect = document.getElementById('patient-gender');
  const phoneInput = document.getElementById('patient-phone');
  const idInput = document.getElementById('patient-id-input');

  const fields = [nameInput, ageInput, genderSelect, phoneInput, idInput].filter(Boolean);
  fields.forEach(field => {
    field.addEventListener('input', () => onPatientFieldChanged());
    field.addEventListener('change', () => onPatientFieldChanged());
  });

  updatePatientSaveButtonState();
}

function onPatientFieldChanged() {
  isPatientSavedForSession = false;
  const saveBtn = document.getElementById('btn-save-patient');
  const btnLabel = document.getElementById('btn-save-patient-label');
  const btnIcon = document.getElementById('btn-save-patient-icon');
  if (saveBtn) {
    saveBtn.classList.remove('btn-saved');
    if (btnLabel) btnLabel.textContent = 'Save Patient Details';
    if (btnIcon) btnIcon.textContent = '✓';
  }

  ['patient-name-input', 'patient-age', 'patient-gender', 'patient-phone', 'patient-id-input'].forEach(id => {
    document.getElementById(id)?.classList.remove('confirmed-field');
  });

  const errBanner = document.getElementById('patient-save-error');
  if (errBanner) errBanner.style.display = 'none';

  updatePatientSaveButtonState();
}

function validatePatientForm() {
  const nameInput = document.getElementById('patient-name-input');
  const ageInput = document.getElementById('patient-age');
  const phoneInput = document.getElementById('patient-phone');

  const name = nameInput ? nameInput.value.trim() : '';
  const ageVal = ageInput ? ageInput.value.trim() : '';

  if (!name) {
    return { valid: false, message: 'Patient name is required.' };
  }

  if (!ageVal) {
    return { valid: false, message: 'Patient age is required.' };
  }

  const age = parseInt(ageVal, 10);
  if (isNaN(age) || age < 1 || age > 120) {
    return { valid: false, message: 'Please enter a valid age between 1 and 120.' };
  }

  return { valid: true, name, age, phone: phoneInput ? phoneInput.value.trim() : '' };
}

function updatePatientSaveButtonState() {
  const saveBtn = document.getElementById('btn-save-patient');
  if (!saveBtn) return;
  const val = validatePatientForm();
  saveBtn.disabled = !val.valid;
}

async function savePatientDetails(silent = false) {
  const val = validatePatientForm();
  const errBanner = document.getElementById('patient-save-error');
  const errText = document.getElementById('patient-save-error-text');
  const saveBtn = document.getElementById('btn-save-patient');
  const btnLabel = document.getElementById('btn-save-patient-label');
  const btnIcon = document.getElementById('btn-save-patient-icon');

  if (!val.valid) {
    if (!silent) {
      if (errText) errText.textContent = val.message;
      if (errBanner) errBanner.style.display = 'block';
    }
    return null;
  }

  const genderSelect = document.getElementById('patient-gender');
  const idInput = document.getElementById('patient-id-input');
  const name = val.name;
  const age = val.age;
  const gender = genderSelect ? genderSelect.value : 'Male';
  const phone = val.phone;
  const patientCode = idInput ? idInput.value.trim() : '';

  if (!silent && btnLabel) {
    if (saveBtn) saveBtn.disabled = true;
    btnLabel.textContent = 'Saving to Database...';
    if (btnIcon) btnIcon.textContent = '⏳';
  }

  try {
    const res = await fetch('/api/patients/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        patient_code: patientCode,
        age,
        gender,
        phone
      })
    });

    let data = null;
    try {
      data = await res.json();
    } catch (parseErr) {
      console.error('Response JSON parse error:', parseErr);
      const errTextContent = `Server returned HTTP ${res.status} (${res.statusText || 'Non-JSON response'}). Please ensure the server is active.`;
      if (errText) errText.textContent = errTextContent;
      if (errBanner) errBanner.style.display = 'block';
      if (saveBtn) saveBtn.disabled = false;
      if (btnLabel) btnLabel.textContent = 'Save Patient Details';
      if (btnIcon) btnIcon.textContent = '✓';
      return null;
    }

    if (!res.ok || !data.success) {
      const msg = data.error || data.message || `Save failed with HTTP ${res.status} (${res.statusText || 'Error'})`;
      if (errText) errText.textContent = msg;
      if (errBanner) errBanner.style.display = 'block';
      if (saveBtn) saveBtn.disabled = false;
      if (btnLabel) btnLabel.textContent = 'Save Patient Details';
      if (btnIcon) btnIcon.textContent = '✓';
      return null;
    }

    activePatientId = data.patient.id;
    isPatientSavedForSession = true;

    if (idInput) {
      idInput.value = data.patient.patient_code || `CS-${data.patient.id + 9040}`;
    }

    if (errBanner) errBanner.style.display = 'none';

    const alertBanner = document.getElementById('patient-alert-banner');
    const alertText = document.getElementById('patient-alert-text');
    if (alertBanner && alertText) {
      if (data.visit_count && data.visit_count > 0) {
        alertText.innerHTML = `Linked existing patient records for <strong>${data.patient.name}</strong> (${data.visit_count} past diagnostic visits on file).`;
      } else {
        alertText.innerHTML = `✓ Patient record <strong>${data.patient.name}</strong> (${data.patient.patient_code}) successfully saved to database. Ready for diagnostic scan.`;
      }
      alertBanner.style.display = 'block';
    }

    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.classList.add('btn-saved');
    }
    if (btnLabel) btnLabel.textContent = 'Patient Record Saved ✓';
    if (btnIcon) btnIcon.textContent = '✓';

    ['patient-name-input', 'patient-age', 'patient-gender', 'patient-phone', 'patient-id-input'].forEach(id => {
      document.getElementById(id)?.classList.add('confirmed-field');
    });

    loadPatientRecordsFromDB();
    loadAnalyticsFromDB();

    return data.patient;

  } catch (e) {
    console.error('Error saving patient details:', e);
    const detailMsg = e && e.message ? ` (${e.message})` : '';
    if (errText) errText.textContent = `Could not reach server${detailMsg}. Please check network or verify server is active.`;
    if (errBanner) errBanner.style.display = 'block';
    if (saveBtn) saveBtn.disabled = false;
    if (btnLabel) btnLabel.textContent = 'Save Patient Details';
    if (btnIcon) btnIcon.textContent = '✓';
    return null;
  }
}

async function checkPatientAutoAccess() {
  const nameInput = document.getElementById('patient-name-input');
  const alertBanner = document.getElementById('patient-alert-banner');
  const alertText = document.getElementById('patient-alert-text');
  if (!nameInput || !alertBanner) return;

  const query = nameInput.value.trim().toLowerCase();
  updatePatientSaveButtonState();

  if (!query) {
    alertBanner.style.display = 'none';
    return;
  }

  try {
    const res = await fetch('/api/patients');
    const patients = await res.json();
    const match = patients.find(p => p.name.toLowerCase().includes(query) || (p.patient_code && p.patient_code.toLowerCase().includes(query)));

    if (match) {
      activePatientId = match.id;
      const idInput = document.getElementById('patient-id-input');
      const ageInput = document.getElementById('patient-age');
      const genderSelect = document.getElementById('patient-gender');
      const phoneInput = document.getElementById('patient-phone');

      if (idInput && !idInput.value) idInput.value = match.patient_code || `CS-${match.id + 9040}`;
      if (ageInput && match.age) ageInput.value = match.age;
      if (genderSelect && match.gender) genderSelect.value = match.gender;
      if (phoneInput && match.phone) phoneInput.value = match.phone;

      const visitRes = await fetch(`/api/patients/${match.id}/visits`);
      const visitData = await visitRes.json();
      const visitCount = visitData.visits ? visitData.visits.length : 0;

      alertText.innerHTML = `Linked existing patient records for <strong>${match.name}</strong> (${visitCount} past diagnostic visits on file).`;
      alertBanner.style.display = 'block';
    } else {
      alertBanner.style.display = 'none';
    }
  } catch (e) {
    alertBanner.style.display = 'none';
  }
}

/* --------------------------------------------------------------------------
   4. Drag & Drop Upload Zone & Confirmation Preview Card State
   -------------------------------------------------------------------------- */
function initDragAndDrop() {
  const dropzone = document.getElementById('upload-dropzone');
  if (!dropzone) return;

  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
  });

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
  });

  dropzone.addEventListener('drop', handleDrop, false);
}

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

function handleDrop(e) {
  const dt = e.dataTransfer;
  const files = dt.files;
  if (files.length) handleFile(files[0]);
}

function setUploadMode(mode) {
  currentUploadMode = mode;
  document.getElementById('btn-mode-single').style.background = (mode === 'single') ? 'linear-gradient(135deg, var(--c-electric-blue), var(--c-violet))' : 'rgba(255,255,255,0.1)';
  document.getElementById('btn-mode-smear').style.background = (mode === 'smear') ? 'linear-gradient(135deg, var(--c-electric-blue), var(--c-violet))' : 'rgba(255,255,255,0.1)';

  const text = document.getElementById('dropzone-text');
  if (text) {
    if (mode === 'single') {
      text.textContent = 'Drop single cropped cell image here or click to browse';
    } else {
      text.textContent = 'Drop full field-of-view smear image here or click to browse';
    }
  }

  const modeText = document.getElementById('preview-mode-text');
  if (modeText) {
    modeText.textContent = (mode === 'single') ? 'Single Cell Mode' : 'Full Smear Mode';
  }
}

function handleFileSelect(e) {
  if (e.target.files.length) {
    handleFile(e.target.files[0]);
  }
}

function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '45.2 KB';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function handleFile(file) {
  if (!file.type.startsWith('image/')) {
    alert('Please upload a valid blood cell image file (PNG, JPG, or TIFF).');
    return;
  }

  currentFile = file;

  const reader = new FileReader();
  reader.onload = (evt) => {
    displayUploadPreview(evt.target.result, file.name, file.size);
  };
  reader.readAsDataURL(file);
}

function displayUploadPreview(imgDataUrl, filename, sizeBytes) {
  const dropzone = document.getElementById('upload-dropzone');
  const previewCard = document.getElementById('upload-preview-card');
  const thumbImg = document.getElementById('preview-thumbnail-img');
  const filenameEl = document.getElementById('preview-filename-text');
  const sizeEl = document.getElementById('preview-filesize-text');
  const modeEl = document.getElementById('preview-mode-text');
  const btnRun = document.getElementById('btn-run-ai');
  const btnLabel = document.getElementById('btn-run-ai-label');

  if (thumbImg) thumbImg.src = imgDataUrl;
  if (filenameEl) filenameEl.textContent = filename || 'microscopy_cell_scan.png';
  if (sizeEl) sizeEl.textContent = formatFileSize(sizeBytes);
  if (modeEl) modeEl.textContent = (currentUploadMode === 'single') ? 'Single Cell Mode' : 'Full Smear Mode';

  if (dropzone) dropzone.style.display = 'none';
  if (previewCard) previewCard.style.display = 'flex';

  if (btnRun) {
    btnRun.disabled = false;
    btnRun.classList.add('btn-pulse');
  }
  if (btnLabel) {
    btnLabel.textContent = 'Run MobileNetV2 Diagnosis';
  }
}

function removeUploadedImage(event) {
  if (event) event.stopPropagation();

  currentFile = null;
  const fileInput = document.getElementById('cell-file-input');
  if (fileInput) fileInput.value = '';

  const dropzone = document.getElementById('upload-dropzone');
  const previewCard = document.getElementById('upload-preview-card');
  const btnRun = document.getElementById('btn-run-ai');
  const btnLabel = document.getElementById('btn-run-ai-label');
  const resultPanel = document.getElementById('diagnosis-result-panel');

  if (previewCard) previewCard.style.display = 'none';
  if (dropzone) dropzone.style.display = 'block';

  if (btnRun) {
    btnRun.disabled = true;
    btnRun.classList.remove('btn-pulse');
  }
  if (btnLabel) {
    btnLabel.textContent = 'Select or drop an image to run diagnosis';
  }
  if (resultPanel) {
    resultPanel.style.display = 'none';
  }
}

/* Quick Sample Preset Generators with Realistic Microscopy Morphology */
function loadSampleImage(type) {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext('2d');

  // Realistic dark microscope backdrop
  ctx.fillStyle = '#060a12';
  ctx.fillRect(0, 0, 256, 256);

  // Subtle circular optical illumination vignette
  const bgGrad = ctx.createRadialGradient(128, 128, 20, 128, 128, 128);
  bgGrad.addColorStop(0, 'rgba(30, 41, 59, 0.7)');
  bgGrad.addColorStop(1, 'rgba(6, 10, 18, 0.95)');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, 256, 256);

  let filename = '';
  let approxBytes = 48500;

  if (type === 'parasitized') {
    setUploadMode('single');
    filename = 'sample_parasitized_cell_P_falciparum.png';
    approxBytes = 56200;

    // Biconcave RBC Body
    const rbcGrad = ctx.createRadialGradient(115, 115, 15, 128, 128, 80);
    rbcGrad.addColorStop(0, '#f472b6');
    rbcGrad.addColorStop(0.7, '#db2777');
    rbcGrad.addColorStop(1, '#9d174d');

    ctx.beginPath();
    ctx.arc(128, 128, 82, 0, Math.PI * 2);
    ctx.fillStyle = rbcGrad;
    ctx.shadowColor = '#ec4899';
    ctx.shadowBlur = 16;
    ctx.fill();
    ctx.shadowBlur = 0;

    // Pale central pallor
    ctx.beginPath();
    ctx.arc(128, 128, 30, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(251, 207, 232, 0.5)';
    ctx.fill();

    // Plasmodium falciparum Ring Trophozoite (Giemsa Violet Ring + Chromatin Dot)
    ctx.beginPath();
    ctx.arc(110, 108, 18, 0, Math.PI * 2);
    ctx.lineWidth = 4;
    ctx.strokeStyle = '#6d28d9';
    ctx.stroke();

    // Chromatin Ruby Dot
    ctx.beginPath();
    ctx.arc(124, 98, 5.5, 0, Math.PI * 2);
    ctx.fillStyle = '#f43f5e';
    ctx.shadowColor = '#f43f5e';
    ctx.shadowBlur = 10;
    ctx.fill();
    ctx.shadowBlur = 0;

  } else if (type === 'uninfected') {
    setUploadMode('single');
    filename = 'sample_uninfected_normal_rbc.png';
    approxBytes = 42100;

    // Normal Healthy Erythrocyte
    const rbcGrad = ctx.createRadialGradient(120, 120, 15, 128, 128, 80);
    rbcGrad.addColorStop(0, '#34d399');
    rbcGrad.addColorStop(0.7, '#059669');
    rbcGrad.addColorStop(1, '#064e3b');

    ctx.beginPath();
    ctx.arc(128, 128, 80, 0, Math.PI * 2);
    ctx.fillStyle = rbcGrad;
    ctx.shadowColor = '#10b981';
    ctx.shadowBlur = 14;
    ctx.fill();
    ctx.shadowBlur = 0;

    // Clean normal central pallor
    ctx.beginPath();
    ctx.arc(128, 128, 32, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(167, 243, 208, 0.45)';
    ctx.fill();

  } else {
    setUploadMode('smear');
    filename = 'sample_blood_smear_full_field.png';
    approxBytes = 84600;

    // Multiple RBCs across smear field
    const cells = [
      { x: 70, y: 70, r: 36, infected: false },
      { x: 170, y: 80, r: 38, infected: true },
      { x: 80, y: 170, r: 35, infected: false },
      { x: 180, y: 180, r: 37, infected: true },
      { x: 128, y: 128, r: 34, infected: false },
      { x: 215, y: 120, r: 28, infected: false },
      { x: 40, y: 125, r: 30, infected: false }
    ];

    cells.forEach(c => {
      ctx.beginPath();
      ctx.arc(c.x, c.y, c.r, 0, Math.PI * 2);
      ctx.fillStyle = c.infected ? '#db2777' : '#059669';
      ctx.fill();

      // Inner pallor
      ctx.beginPath();
      ctx.arc(c.x, c.y, c.r * 0.4, 0, Math.PI * 2);
      ctx.fillStyle = c.infected ? 'rgba(251, 207, 232, 0.4)' : 'rgba(167, 243, 208, 0.4)';
      ctx.fill();

      if (c.infected) {
        ctx.beginPath();
        ctx.arc(c.x - 6, c.y - 6, 8, 0, Math.PI * 2);
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = '#6d28d9';
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(c.x, c.y - 10, 3, 0, Math.PI * 2);
        ctx.fillStyle = '#f43f5e';
        ctx.fill();
      }
    });
  }

  canvas.toBlob((blob) => {
    currentFile = new File([blob], filename, { type: 'image/png' });
    const dataUrl = canvas.toDataURL('image/png');
    displayUploadPreview(dataUrl, filename, approxBytes);
  }, 'image/png');
}

/* --------------------------------------------------------------------------
   5. Multi-Stage Inference Pipeline Execution
   -------------------------------------------------------------------------- */
async function runDiagnostics() {
  const val = validatePatientForm();
  if (!val.valid) {
    alert(val.message);
    const nameInput = document.getElementById('patient-name-input');
    if (nameInput && !nameInput.value.trim()) nameInput.focus();
    return;
  }

  if (!currentFile) {
    alert('Please drop or select a cell image first.');
    return;
  }

  // Ensure patient is persisted to DB before running inference
  let patientRecord = null;
  if (!isPatientSavedForSession) {
    patientRecord = await savePatientDetails(false);
    if (!patientRecord) {
      return;
    }
  }

  const name = document.getElementById('patient-name-input')?.value.trim() || val.name;
  const age = document.getElementById('patient-age')?.value || val.age;
  const gender = document.getElementById('patient-gender')?.value || 'Female';
  const phone = document.getElementById('patient-phone')?.value || '';
  const patientCode = document.getElementById('patient-id-input')?.value.trim() || (patientRecord ? patientRecord.patient_code : '');

  // Show Multi-stage Progress Loader
  const loaderOverlay = document.getElementById('inference-loader');
  const stageText = document.getElementById('loader-stage-text');
  const subtextEl = document.getElementById('loader-subtext');
  const progressFill = document.getElementById('loader-progress-fill');

  if (loaderOverlay) loaderOverlay.style.display = 'flex';
  if (stageText) stageText.textContent = 'Loading MobileNetV2 Model...';
  if (subtextEl) subtextEl.textContent = 'Initializing convolutional feature extraction pipeline';
  if (progressFill) progressFill.style.width = '25%';

  const stageTimer1 = setTimeout(() => {
    if (stageText) stageText.textContent = 'Analyzing Cell Morphology & Staining...';
    if (subtextEl) subtextEl.textContent = 'Evaluating erythrocyte borders, pallor, and chromatin inclusion markers';
    if (progressFill) progressFill.style.width = '55%';
  }, 400);

  const stageTimer2 = setTimeout(() => {
    if (stageText) stageText.textContent = 'Generating Grad-CAM Explainability Map...';
    if (subtextEl) subtextEl.textContent = 'Computing gradients on top convolutional layer and compositing jet colormap';
    if (progressFill) progressFill.style.width = '80%';
  }, 800);

  const stageTimer3 = setTimeout(() => {
    if (stageText) stageText.textContent = 'Evaluating Risk Tier & Persisting Database Record...';
    if (subtextEl) subtextEl.textContent = 'Logging visit history and clinical treatment framework';
    if (progressFill) progressFill.style.width = '95%';
  }, 1200);

  const formData = new FormData();
  formData.append('name', name);
  formData.append('patient_code', patientCode);
  formData.append('age', age);
  formData.append('gender', gender);
  formData.append('phone', phone);
  formData.append('mode', currentUploadMode);
  formData.append('image', currentFile);

  try {
    const res = await fetch('/api/diagnose', { method: 'POST', body: formData });
    const data = await res.json();

    clearTimeout(stageTimer1);
    clearTimeout(stageTimer2);
    clearTimeout(stageTimer3);

    if (!res.ok || !data.success) {
      if (loaderOverlay) loaderOverlay.style.display = 'none';
      alert(data.error || 'Failed to complete diagnostic evaluation.');
      return;
    }

    currentDiagnosisData = data.diagnosis;
    currentVisitId = data.diagnosis.visit_id;
    activePatientId = data.patient.id;

    if (progressFill) progressFill.style.width = '100%';

    setTimeout(() => {
      if (loaderOverlay) loaderOverlay.style.display = 'none';
      renderDiagnosisResult(data.diagnosis, data.patient);
      loadPatientRecordsFromDB();
      loadAnalyticsFromDB();
    }, 300);

  } catch (e) {
    clearTimeout(stageTimer1);
    clearTimeout(stageTimer2);
    clearTimeout(stageTimer3);
    if (loaderOverlay) loaderOverlay.style.display = 'none';
    console.error(e);
    alert('Network or server error during diagnosis processing.');
  }
}

/* --------------------------------------------------------------------------
   6. Render Rich Results Display (Side-by-Side + Grad-CAM + Risk Meter)
   -------------------------------------------------------------------------- */
function renderDiagnosisResult(diag, patient) {
  const panel = document.getElementById('diagnosis-result-panel');
  if (!panel) return;

  const isPositive = diag.label === 'Parasitized' || diag.parasitemia_pct > 0;

  // Header & Badges
  document.getElementById('res-visit-num').textContent = diag.visit_id;
  document.getElementById('res-badge-mode').textContent = (currentUploadMode === 'single') ? 'Single Cell Micro-Scan' : 'Full Smear Field AI Analysis';

  // Confidence & Verdict Readout
  const confPctEl = document.getElementById('res-confidence-pct');
  const verdictTitleEl = document.getElementById('res-verdict-title');
  const verdictDescEl = document.getElementById('res-verdict-desc');

  confPctEl.textContent = `${diag.confidence_score}%`;
  
  if (isPositive) {
    verdictTitleEl.textContent = `PARASITIZED (P. falciparum-consistent)`;
    verdictTitleEl.style.color = 'var(--c-pink-light)';
    verdictDescEl.textContent = `Intracellular ring trophozoites identified. Parasitemia rate: ${diag.parasitemia_pct}%.`;
  } else {
    verdictTitleEl.textContent = `UNINFECTED (Clear Erythrocyte)`;
    verdictTitleEl.style.color = 'var(--c-green-light)';
    verdictDescEl.textContent = `No intracellular Plasmodium parasites or ring forms detected in this sample.`;
  }

  // Side-by-side Images
  const origImg = document.getElementById('res-original-img');
  const gradcamImg = document.getElementById('res-gradcam-img');

  if (origImg && diag.image_data) origImg.src = diag.image_data;
  if (gradcamImg && diag.heatmap_data) gradcamImg.src = diag.heatmap_data;

  // Semi-Circular Risk Meter Gauge Needle & Dynamic Tagline
  const riskTierPill = document.getElementById('res-risk-tier-pill');
  const riskBadgeLabel = document.getElementById('res-risk-badge-label');
  const riskTaglineText = document.getElementById('res-risk-tagline-text');
  const riskSubtext = document.getElementById('res-risk-subtext');
  const riskTaglineCard = document.getElementById('res-risk-tagline-card');
  const needleGroup = document.getElementById('gauge-needle-group');

  const riskBand = diag.risk_band || (isPositive ? 'High risk' : 'Negative / Clear');
  const bandKey = (diag.band || '').toLowerCase();
  const riskVal = (diag.risk_value !== undefined) ? diag.risk_value : (isPositive ? 80 : 10);
  const tagline = diag.risk_tagline || (isPositive ? 'Parasitemia detected. Medical evaluation advised.' : 'All clear — no parasites detected');

  riskTierPill.textContent = riskBand;
  riskBadgeLabel.textContent = `${riskBand.toUpperCase()} LEVEL`;
  riskTaglineText.textContent = `"${tagline}"`;

  // Color Mapping according to 5 Risk Bands
  let bandColor = 'var(--c-green)';
  let borderColor = 'var(--c-green)';
  let pillBg = 'rgba(16, 185, 129, 0.2)';
  let pillColor = 'var(--c-green-light)';
  let subtextMessage = 'Routine follow-up only. No immediate treatment needed.';

  if (riskBand === 'Negative / Clear' || bandKey === 'clear') {
    bandColor = '#10b981';
    borderColor = '#10b981';
    pillBg = 'rgba(16, 185, 129, 0.2)';
    pillColor = '#34d399';
    subtextMessage = 'Normal erythrocyte morphology with clear cytoplasmic central pallor.';
  } else if (riskBand === 'Low risk' || bandKey === 'low') {
    bandColor = '#84cc16';
    borderColor = '#84cc16';
    pillBg = 'rgba(132, 204, 22, 0.2)';
    pillColor = '#a3e635';
    subtextMessage = 'Mild uncertainty detected in scan. Retest if fever or chills develop.';
  } else if (riskBand === 'Moderate risk' || bandKey === 'moderate') {
    bandColor = '#facc15';
    borderColor = '#facc15';
    pillBg = 'rgba(250, 204, 21, 0.2)';
    pillColor = '#fde047';
    subtextMessage = 'Recommend retesting within 24–48 hours or confirming via Giemsa thick smear.';
  } else if (riskBand === 'High risk' || bandKey === 'high') {
    bandColor = '#f97316';
    borderColor = '#f97316';
    pillBg = 'rgba(249, 115, 22, 0.2)';
    pillColor = '#fdba74';
    subtextMessage = 'High confidence parasitemia detected. Consult a physician promptly.';
  } else if (riskBand === 'Critical risk' || bandKey === 'critical') {
    bandColor = '#ef4444';
    borderColor = '#ef4444';
    pillBg = 'rgba(239, 68, 68, 0.25)';
    pillColor = '#fca5a5';
    subtextMessage = 'High parasite burden detected (>7% parasitemia). Urgent medical care recommended.';
  }

  riskTierPill.style.background = pillBg;
  riskTierPill.style.color = pillColor;
  riskTierPill.style.borderColor = bandColor;

  riskTaglineCard.style.borderLeftColor = borderColor;
  riskBadgeLabel.style.color = bandColor;
  riskSubtext.textContent = subtextMessage;

  // Calculate Needle Rotation (-90deg at 0% to +90deg at 100%)
  const angle = (diag.needle_angle !== undefined) ? diag.needle_angle : (-90 + (Math.max(0, Math.min(100, riskVal)) / 100) * 180);
  if (needleGroup) {
    needleGroup.style.transformOrigin = '120px 120px';
    needleGroup.style.transform = `rotate(${angle}deg)`;
    needleGroup.setAttribute('transform', `rotate(${angle}, 120, 120)`);
  }

  panel.style.display = 'block';
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function resetDiagnosisForm() {
  removeUploadedImage();
  const panel = document.getElementById('diagnosis-result-panel');
  if (panel) panel.style.display = 'none';
  window.scrollTo({ top: 300, behavior: 'smooth' });
}

function viewActivePatientAnalytics() {
  switchTab('analytics');
  selectPatientAnalytics(activePatientId);
}

function downloadCurrentVisitPDF() {
  if (!currentVisitId) {
    alert('No active diagnosis visit available for export.');
    return;
  }
  window.open(`/api/visits/${currentVisitId}/report`, '_blank');
}

/* --------------------------------------------------------------------------
   7. Real Database-Backed Patient Records (All Visits Newest First)
   -------------------------------------------------------------------------- */
async function loadPatientRecordsFromDB() {
  const tbody = document.getElementById('db-patient-records-tbody');
  if (!tbody) return;

  try {
    const res = await fetch('/api/patient-records');
    const records = await res.json();

    tbody.innerHTML = '';

    if (!records || records.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color: var(--text-muted); padding: 24px;">No saved patient records found in database. Run a diagnosis test to create one.</td></tr>';
      return;
    }

    records.forEach((r) => {
      const isPositive = r.diagnosis_result === 'Parasitized' || r.diagnosis_result === 'Malaria Detected' || (r.parasitemia_pct && r.parasitemia_pct > 0);
      const riskBand = r.risk_band || (isPositive ? 'High risk' : 'Negative / Clear');
      const visitDate = r.visit_date || (r.patient_created_at ? r.patient_created_at.split('T')[0] : '2026-08-14');
      const confScore = r.confidence_score ? `${r.confidence_score}%` : '95.0%';

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong style="font-family: var(--font-mono); color: var(--c-cyan-light);">${r.patient_code || ('CS-' + (r.patient_id + 9040))}</strong></td>
        <td><strong>${r.name}</strong></td>
        <td>${r.age || 30}</td>
        <td>${r.gender || 'Male'}</td>
        <td>${visitDate}</td>
        <td>
          <span style="font-weight: 700; color: ${isPositive ? 'var(--c-pink-light)' : 'var(--c-green-light)'}; display: inline-flex; align-items: center; gap: 6px;">
            <span>${isPositive ? '🔴' : '🟢'}</span>
            <span>${r.diagnosis_result ? r.diagnosis_result.toUpperCase() : (isPositive ? 'PARASITIZED' : 'UNINFECTED')}</span>
          </span>
        </td>
        <td>
          <div style="font-size: 0.85rem; font-weight: 600;">
            <span>${confScore}</span> · 
            <span style="color: ${isPositive ? '#fca5a5' : 'var(--c-green-light)'};">${riskBand}</span>
          </div>
        </td>
        <td>
          <div style="display: flex; gap: 6px;">
            <button class="btn-sm-secondary" style="font-size: 0.76rem; padding: 4px 10px;" onclick="openPatientVisitReport(${r.visit_id || r.patient_id})">
              View Report 📄
            </button>
            <button class="btn-sm-secondary" style="font-size: 0.76rem; padding: 4px 8px;" onclick="window.open('/api/visits/${r.visit_id}/report', '_blank')" title="Download PDF Report">
              ⬇️ PDF
            </button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error('Error fetching DB patient records:', e);
  }
}

/* --------------------------------------------------------------------------
   8. Patient Visit Report Modal
   -------------------------------------------------------------------------- */
async function openPatientVisitReport(visitId) {
  currentModalVisitId = visitId;
  try {
    const res = await fetch(`/api/visits/${visitId}/details`);
    if (!res.ok) {
      // Fallback to patient visits
      const pRes = await fetch(`/api/patients/${visitId}/visits`);
      const pData = await pRes.json();
      populateReportModalWithPatientData(pData.patient, pData.visits || []);
      return;
    }

    const visit = await res.json();
    populateReportModalWithVisitData(visit);

  } catch (e) {
    console.error('Error fetching visit report:', e);
  }
}

function populateReportModalWithVisitData(visit) {
  document.getElementById('rep-name').textContent = visit.patient_name || visit.name || 'Anonymous Patient';
  document.getElementById('rep-id').textContent = visit.patient_code || `CS-${visit.patient_id + 9040}`;
  document.getElementById('rep-age-gender').textContent = `${visit.age || 30} / ${visit.gender || 'Male'}`;
  document.getElementById('rep-phone').textContent = visit.phone || 'N/A';
  document.getElementById('report-date-stamp').textContent = `Date: ${visit.visit_date || '2026-08-14'}`;

  const isPositive = visit.diagnosis_result === 'Parasitized' || visit.diagnosis_result === 'Malaria Detected' || visit.parasitemia_pct > 0;
  const box = document.getElementById('rep-verdict-box');
  const verdictEl = document.getElementById('rep-verdict');
  const riskBandEl = document.getElementById('rep-risk-band');
  const confEl = document.getElementById('rep-confidence');
  const taglineEl = document.getElementById('rep-tagline');

  box.style.background = isPositive ? '#fff1f2' : '#f0fdf4';
  box.style.borderColor = isPositive ? '#e11d48' : '#10b981';

  verdictEl.textContent = `DIAGNOSIS: ${visit.diagnosis_result ? visit.diagnosis_result.toUpperCase() : (isPositive ? 'PARASITIZED' : 'UNINFECTED')}`;
  verdictEl.style.color = isPositive ? '#9f1239' : '#047857';

  riskBandEl.textContent = visit.risk_band || (isPositive ? 'High Risk' : 'Negative / Clear');
  riskBandEl.style.color = isPositive ? '#9f1239' : '#047857';

  confEl.textContent = `${visit.confidence_score || 95.0}% Confidence (Parasitemia: ${visit.parasitemia_pct || 0}%)`;
  taglineEl.textContent = `"${visit.risk_tagline || (isPositive ? 'Parasitemia detected. Medical evaluation advised.' : 'All clear — no parasites detected')}"`;

  // Images in modal
  const origImg = document.getElementById('rep-img-original');
  const gradImg = document.getElementById('rep-img-gradcam');

  if (visit.image_data) {
    origImg.src = visit.image_data;
    origImg.style.display = 'inline-block';
  } else {
    origImg.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="%23eee"/><text x="60" y="65" font-size="10" text-anchor="middle">No Image</text></svg>';
  }

  if (visit.heatmap_data) {
    gradImg.src = visit.heatmap_data;
    gradImg.style.display = 'inline-block';
  } else {
    gradImg.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="%23eee"/><text x="60" y="65" font-size="10" text-anchor="middle">No Grad-CAM</text></svg>';
  }

  // Prescription Rx Guidelines
  const rxContent = document.getElementById('rep-rx-content');
  if (isPositive) {
    rxContent.innerHTML = `
      • <strong>Chemotherapy:</strong> Artemether-Lumefantrine (Coartem 80/480mg) 6-dose oral course.<br>
      • <strong>Supportive Care:</strong> Paracetamol 500mg as needed for pyrexia; oral/IV fluid rehydration.<br>
      • <strong>Clinical Protocol:</strong> Repeat Giemsa blood smear in 48-72 hours to verify clearance.
    `;
  } else {
    rxContent.innerHTML = `
      • <strong>Chemotherapy:</strong> No antimalarial chemotherapy indicated.<br>
      • <strong>Supportive Care:</strong> Standard rest, hydration, and symptomatic care if non-malarial fever occurs.<br>
      • <strong>Protocol:</strong> Routine follow-up if symptoms persist.
    `;
  }

  document.getElementById('report-modal').classList.add('show');
}

function populateReportModalWithPatientData(patient, visits) {
  const latest = visits.length ? visits[visits.length - 1] : {};
  latest.patient_name = patient.name;
  latest.patient_code = patient.patient_code;
  latest.age = patient.age;
  latest.gender = patient.gender;
  latest.phone = patient.phone;
  populateReportModalWithVisitData(latest);
}

function closeReportModal() {
  document.getElementById('report-modal').classList.remove('show');
}

function downloadActiveVisitPDF() {
  if (currentModalVisitId) {
    window.open(`/api/visits/${currentModalVisitId}/report`, '_blank');
  } else if (activePatientId) {
    window.open(`/api/patients/${activePatientId}/report`, '_blank');
  }
}

function downloadPatientFullReportPDF() {
  if (activePatientId) {
    window.open(`/api/patients/${activePatientId}/report`, '_blank');
  }
}

/* --------------------------------------------------------------------------
   9. Redesigned Patient-Centric & Global Analytics
   -------------------------------------------------------------------------- */
function switchAnalyticsView(viewMode) {
  const btnAll = document.getElementById('btn-analytics-all');
  const btnPatient = document.getElementById('btn-analytics-patient');
  const viewAll = document.getElementById('view-analytics-all');
  const viewPatient = document.getElementById('view-analytics-patient');
  const filterInfo = document.getElementById('analytics-filter-info');

  if (viewMode === 'all') {
    btnAll.classList.add('active');
    btnPatient.classList.remove('active');
    viewAll.style.display = 'block';
    viewPatient.style.display = 'none';
    filterInfo.textContent = 'Showing aggregate analytics across all registered patient visits';
  } else {
    btnPatient.classList.add('active');
    btnAll.classList.remove('active');
    viewPatient.style.display = 'block';
    viewAll.style.display = 'none';
    filterInfo.textContent = 'Filtered to individual patient longitudinal history';
  }
}

async function loadAnalyticsFromDB() {
  try {
    const res = await fetch('/api/analytics-data');
    const data = await res.json();

    document.getElementById('stat-total-screenings').textContent = data.total_screenings || 0;
    document.getElementById('stat-positive-count').textContent = data.positive_cases || 0;
    document.getElementById('stat-negative-count').textContent = data.negative_cases || 0;

    renderScatterAgeChart(data.scatter_age_parasitemia);
    renderTimeSeriesChart(data.time_series);
    renderRatioBarChart(data.positive_cases, data.negative_cases);

    // Populate Patient Directory in Analytics
    renderAnalyticsPatientsList(data.patients_list || []);

    // Load Default Active Patient Analytics
    if (activePatientId) {
      loadIndividualPatientAnalytics(activePatientId);
    }
  } catch (e) {
    console.error('Error fetching DB analytics:', e);
  }
}

function renderAnalyticsPatientsList(patients) {
  const tbody = document.getElementById('analytics-patients-list-tbody');
  if (!tbody) return;

  tbody.innerHTML = '';
  if (!patients || patients.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color: var(--text-muted); padding: 16px;">No patients on file.</td></tr>';
    return;
  }

  patients.forEach(p => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong style="font-family: var(--font-mono); color: var(--c-cyan-light);">${p.patient_code || ('CS-' + (p.id + 9040))}</strong></td>
      <td><strong>${p.name}</strong></td>
      <td>${p.age || 30} / ${p.gender || 'Male'}</td>
      <td><span class="badge-tag">${p.visit_count || 1} Tests</span></td>
      <td>${p.last_visit || (p.created_at ? p.created_at.split('T')[0] : '2026-08-14')}</td>
      <td>
        <button class="btn-action" style="font-size: 0.78rem; padding: 5px 12px; background: linear-gradient(135deg, var(--c-cyan), var(--c-electric-blue));" onclick="selectPatientAnalytics(${p.id})">
          View Analytics 📊
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function selectPatientAnalytics(patientId) {
  activePatientId = patientId;
  await loadIndividualPatientAnalytics(patientId);
  switchAnalyticsView('patient');
}

async function loadIndividualPatientAnalytics(patientId) {
  try {
    const res = await fetch(`/api/patients/${patientId}/analytics`);
    if (!res.ok) return;
    const data = await res.json();

    const p = data.patient;
    document.getElementById('active-patient-name-tab').textContent = p.name;
    document.getElementById('patient-view-name').textContent = p.name;
    document.getElementById('patient-view-code').textContent = p.patient_code || `CS-${p.id + 9040}`;
    document.getElementById('patient-view-demog').textContent = `${p.age || 30} / ${p.gender || 'Male'}`;
    document.getElementById('patient-view-phone').textContent = p.phone || 'N/A';

    document.getElementById('pt-stat-total').textContent = data.total_tests || 0;
    document.getElementById('pt-stat-positive').textContent = data.positive_count || 0;
    document.getElementById('pt-stat-latest').textContent = data.latest_result || 'Uninfected';
    document.getElementById('pt-stat-latest').style.color = (data.latest_result === 'Parasitized' || data.latest_result === 'Malaria Detected') ? 'var(--c-pink-light)' : 'var(--c-green-light)';
    document.getElementById('pt-stat-trend').textContent = data.trend_indicator || 'Initial screening recorded.';

    renderPatientTrendChart(data.timeline || []);
    renderPatientTimelineList(data.timeline || []);

  } catch (e) {
    console.error('Error loading patient analytics:', e);
  }
}

function renderPatientTrendChart(timeline) {
  const ctx = document.getElementById('patient-trend-chart');
  if (!ctx) return;
  if (patientTrendChartInstance) patientTrendChartInstance.destroy();

  const labels = timeline.map((t, idx) => `${t.date} (#${idx + 1})`);
  const parasitemiaData = timeline.map(t => t.parasitemia_pct || 0);
  const confidenceData = timeline.map(t => t.confidence || 95);

  patientTrendChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels.length ? labels : ['Visit 1'],
      datasets: [
        {
          label: 'Parasitemia %',
          data: parasitemiaData.length ? parasitemiaData : [0],
          borderColor: '#ec4899',
          backgroundColor: 'rgba(236, 72, 153, 0.15)',
          fill: true,
          tension: 0.25,
          pointRadius: 6,
          pointBackgroundColor: '#ec4899',
          pointHoverRadius: 9,
          yAxisID: 'y'
        },
        {
          label: 'AI Model Confidence %',
          data: confidenceData.length ? confidenceData : [95],
          borderColor: '#06b6d4',
          borderDash: [5, 5],
          tension: 0.25,
          pointRadius: 5,
          pointBackgroundColor: '#06b6d4',
          yAxisID: 'y1'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          labels: { color: '#ddd6fe', font: { family: 'Plus Jakarta Sans', weight: '600' } }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.06)' },
          ticks: { color: '#94a3b8' }
        },
        y: {
          type: 'linear',
          display: true,
          position: 'left',
          beginAtZero: true,
          title: { display: true, text: 'Parasitemia %', color: '#ec4899' },
          grid: { color: 'rgba(255,255,255,0.06)' },
          ticks: { color: '#94a3b8' }
        },
        y1: {
          type: 'linear',
          display: true,
          position: 'right',
          beginAtZero: false,
          min: 50,
          max: 100,
          title: { display: true, text: 'Confidence %', color: '#06b6d4' },
          grid: { drawOnChartArea: false },
          ticks: { color: '#94a3b8' }
        }
      }
    }
  });
}

function renderPatientTimelineList(timeline) {
  const container = document.getElementById('patient-timeline-list');
  if (!container) return;

  container.innerHTML = '';
  if (!timeline || timeline.length === 0) {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.9rem;">No past visit records found.</div>';
    return;
  }

  timeline.forEach((item, idx) => {
    const isPositive = item.label === 'Parasitized' || item.label === 'Malaria Detected' || item.parasitemia_pct > 0;
    const card = document.createElement('div');
    card.className = `timeline-card ${isPositive ? 'positive' : 'negative'}`;
    card.innerHTML = `
      <div>
        <div style="font-size: 0.8rem; color: var(--text-muted); font-family: var(--font-mono);">
          VISIT #${idx + 1} · ${item.date}
        </div>
        <div style="font-family: var(--font-heading); font-size: 1.05rem; font-weight: 700; color: ${isPositive ? 'var(--c-pink-light)' : 'var(--c-green-light)'}; margin-top: 2px;">
          ${isPositive ? '🔴 Parasitized' : '🟢 Uninfected'} (${item.confidence || 95}% Confidence)
        </div>
        <div style="font-size: 0.85rem; color: var(--c-lavender); margin-top: 4px;">
          "${item.risk_tagline || (isPositive ? 'Parasitemia detected.' : 'All clear — no parasites detected')}"
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 12px;">
        <span class="badge-tag" style="background: ${isPositive ? 'rgba(236,72,153,0.15)' : 'rgba(16,185,129,0.15)'}; border-color: ${isPositive ? '#ec4899' : '#10b981'}; color: ${isPositive ? '#f43f5e' : '#34d399'};">
          ${item.risk_band || (isPositive ? 'High risk' : 'Negative / Clear')}
        </span>
        <button class="btn-sm-secondary" onclick="openPatientVisitReport(${item.visit_id})">
          View Details ↗
        </button>
      </div>
    `;
    container.appendChild(card);
  });
}

/* --------------------------------------------------------------------------
   10. Global Data Science Charts (Scatter Plot, Time Series, Ratio)
   -------------------------------------------------------------------------- */
function renderScatterAgeChart(scatterData) {
  const ctx = document.getElementById('scatter-age-chart');
  if (!ctx) return;
  if (scatterAgeChartInstance) scatterAgeChartInstance.destroy();

  const points = scatterData && scatterData.length ? scatterData : [
    { x: 32, y: 6.7, name: 'John Doe', result: 'Parasitized' },
    { x: 27, y: 8.0, name: 'Amina Diallo', result: 'Parasitized' },
    { x: 45, y: 0.0, name: 'Elena Rostova', result: 'Uninfected' },
    { x: 28, y: 5.4, name: 'Vennela Indukuri', result: 'Parasitized' }
  ];

  scatterAgeChartInstance = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [{
        label: 'Patient Diagnoses',
        data: points,
        backgroundColor: points.map(p => p.y > 0 ? '#ec4899' : '#10b981'),
        pointRadius: 7,
        pointHoverRadius: 10
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const raw = ctx.raw;
              return `${raw.name} (Age ${raw.x}): ${raw.result} (${raw.y}%)`;
            }
          }
        }
      },
      scales: {
        x: {
          type: 'linear',
          position: 'bottom',
          title: { display: true, text: 'Patient Age (Years)', color: '#94a3b8' },
          grid: { color: 'rgba(255,255,255,0.08)' },
          ticks: { color: '#94a3b8' }
        },
        y: {
          title: { display: true, text: 'Parasitemia %', color: '#94a3b8' },
          grid: { color: 'rgba(255,255,255,0.08)' },
          ticks: { color: '#94a3b8' }
        }
      }
    }
  });
}

function renderTimeSeriesChart(timeSeriesData) {
  const ctx = document.getElementById('time-series-chart');
  if (!ctx) return;
  if (timeSeriesChartInstance) timeSeriesChartInstance.destroy();

  const points = timeSeriesData && timeSeriesData.length ? timeSeriesData : [
    { x: '2026-08-01', y: 6.7 },
    { x: '2026-08-02', y: 8.0 },
    { x: '2026-08-05', y: 3.1 },
    { x: '2026-08-08', y: 3.6 },
    { x: '2026-08-10', y: 0.0 }
  ];

  timeSeriesChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: points.map(p => p.x),
      datasets: [{
        label: 'Parasitemia Rate %',
        data: points.map(p => p.y),
        borderColor: '#06b6d4',
        backgroundColor: 'rgba(6, 182, 212, 0.15)',
        fill: true,
        tension: 0.25,
        pointRadius: 6,
        pointBackgroundColor: '#ec4899',
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.08)' }, ticks: { color: '#94a3b8' } },
        x: { grid: { color: 'rgba(255,255,255,0.08)' }, ticks: { color: '#94a3b8' } }
      }
    }
  });
}

function renderRatioBarChart(positive, negative) {
  const ctx = document.getElementById('ratio-bar-chart');
  if (!ctx) return;
  if (ratioChartInstance) ratioChartInstance.destroy();

  ratioChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Positive Cases', 'Negative Cases'],
      datasets: [{
        data: [positive || 4, negative || 2],
        backgroundColor: ['#ec4899', '#10b981']
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.08)' }, ticks: { color: '#94a3b8' } },
        x: { grid: { color: 'rgba(255,255,255,0.08)' }, ticks: { color: '#94a3b8' } }
      }
    }
  });
}
