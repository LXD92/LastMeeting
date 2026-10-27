(function (root) {
  'use strict';

  const CONSONANTS = {
    ng: '\uA994', ny: '\uA99A', dh: '\uA99D', th: '\uA99B',
    k: '\uA98F', g: '\uA992', c: '\uA995', j: '\uA997',
    t: '\uA9A0', d: '\uA9A2', n: '\uA9A4', p: '\uA9A5',
    b: '\uA9A7', m: '\uA9A9', y: '\uA9AA', r: '\uA9AB',
    l: '\uA9AD', w: '\uA9AE', s: '\uA9B1', h: '\uA9B2',
    f: '\uA9A5', v: '\uA9A5', z: '\uA997', q: '\uA98F'
  };

  // Unicode signs are used so rendering and conjunct shaping stay with the user's font.
  const VOWELS = {
    a: '', i: '\uA9B6', u: '\uA9B8', e: '\uA9BC',
    'é': '\uA9BA', 'è': '\uA9BA', o: '\uA9BA\uA9B4'
  };

  const CODAS = { ng: '\uA981', r: '\uA982', h: '\uA983' };
  const PANGKON = '\uA9C0';
  const VOWEL_PATTERN = /[aieuoéè]/;

  function readConsonant(text, index) {
    const pair = text.slice(index, index + 2);
    return Object.prototype.hasOwnProperty.call(CONSONANTS, pair) ? pair : text[index];
  }

  function tokenizeWord(word) {
    const lower = word.toLocaleLowerCase('id');
    const units = [];
    for (let index = 0; index < lower.length;) {
      if (VOWEL_PATTERN.test(lower[index])) {
        units.push({ type: 'vowel', value: lower[index] });
        index += 1;
      } else {
        const value = readConsonant(lower, index);
        units.push({ type: 'consonant', value });
        index += value.length;
      }
    }
    return units;
  }

  function transliterateWord(word) {
    const units = tokenizeWord(word);
    const output = [];
    let consonantRun = [];
    let previousBaseIndex = -1;
    let lastVowelIndex = -1;

    for (const unit of units) {
      if (unit.type === 'consonant') {
        consonantRun.push(unit.value);
        continue;
      }

      if (consonantRun.length === 0) {
        output.push('\uA9B2', VOWELS[unit.value]);
      } else {
        for (let index = 0; index < consonantRun.length; index += 1) {
          const base = CONSONANTS[consonantRun[index]];
          if (index > 0) output.push(PANGKON);
          output.push(base);
          previousBaseIndex = output.length - 1;
        }
        output.push(VOWELS[unit.value]);
      }
      consonantRun = [];
      lastVowelIndex = output.length - 1;
    }

    if (consonantRun.length > 0) {
      const finalConsonant = consonantRun[consonantRun.length - 1];
      if (consonantRun.length === 1 && Object.prototype.hasOwnProperty.call(CODAS, finalConsonant) && previousBaseIndex >= 0) {
        output.splice(lastVowelIndex + 1, 0, CODAS[finalConsonant]);
      } else {
        for (let index = 0; index < consonantRun.length; index += 1) {
          output.push(CONSONANTS[consonantRun[index]]);
          if (index < consonantRun.length - 1) output.push(PANGKON);
        }
        output.push(PANGKON);
      }
    }

    return output.join('');
  }

  // Pair-like clusters use pangkon before the following aksara; final r/h/ng use coda signs.
  function transliterate(text) {
    return text.replace(/[a-zéè]+/giu, transliterateWord);
  }

  function prepareInput(text, format) {
    return format === 'lowercase' ? text.toLocaleLowerCase('id') : text;
  }

  const api = { transliterate, transliterateWord, prepareInput };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.JavaneseTranslator = api;

  if (typeof document === 'undefined') return;

  const input = document.getElementById('latin-input');
  const output = document.getElementById('javanese-output');
  const count = document.getElementById('character-count');
  const preview = document.getElementById('processed-preview');
  const caption = document.getElementById('result-caption');
  const error = document.getElementById('error-message');
  const copyStatus = document.getElementById('copy-status');
  const copyButton = document.getElementById('copy-button');
  const downloadButton = document.getElementById('download-button');
  const MAX_SIZE = 58;
  const FONT_STACKS = {
    noto: '"Noto Sans Javanese", "Javanese Text", sans-serif',
    serif: 'serif',
    sans: 'sans-serif'
  };
  let outputSize = 38;
  let debounceTimer;

  function selectedFormat() {
    return document.querySelector('input[name="letter-format"]:checked').value;
  }

  function updateCount() {
    count.textContent = `${input.value.length.toLocaleString('id')} / 5.000 karakter`;
  }

  function updateResult(showEmptyError) {
    const raw = input.value;
    const prepared = prepareInput(raw, selectedFormat());
    updateCount();
    error.hidden = !(showEmptyError && !raw.trim());

    if (!raw.trim()) {
      output.textContent = '';
      preview.textContent = '';
      caption.textContent = 'Hasil akan muncul di sini';
      copyButton.disabled = true;
      downloadButton.disabled = true;
      return;
    }

    output.textContent = transliterate(prepared);
    preview.textContent = `Teks diproses: ${prepared}`;
    caption.textContent = 'Pilih teks untuk menyalin atau gunakan tombol di bawah';
    copyButton.disabled = false;
    downloadButton.disabled = false;
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const temporary = document.createElement('textarea');
    temporary.value = text;
    temporary.style.position = 'fixed';
    temporary.style.opacity = '0';
    document.body.appendChild(temporary);
    temporary.select();
    const copied = document.execCommand('copy');
    temporary.remove();
    if (!copied) throw new Error('Clipboard tidak tersedia');
  }

  document.getElementById('translate-button').addEventListener('click', () => updateResult(true));
  document.getElementById('insert-e-acute').addEventListener('click', () => {
    const start = input.selectionStart;
    const end = input.selectionEnd;
    if (input.value.length - (end - start) >= 5000) return;
    input.setRangeText('é', start, end, 'end');
    input.focus();
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  input.addEventListener('input', () => {
    updateCount();
    error.hidden = true;
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => updateResult(false), 220);
  });
  document.querySelectorAll('input[name="letter-format"]').forEach((radio) => {
    radio.addEventListener('change', () => updateResult(false));
  });
  document.getElementById('clear-button').addEventListener('click', () => {
    input.value = '';
    copyStatus.textContent = '';
    updateResult(false);
    input.focus();
  });
  document.getElementById('example-button').addEventListener('click', () => {
    input.value = 'Aku bocah sing sregep banget. Tangi gasik rewangi ibuku nyapu. Terus aku kudu adus esuk.';
    updateResult(false);
  });
  copyButton.addEventListener('click', async () => {
    try {
      await copyText(output.textContent);
      copyStatus.textContent = 'Hasil berhasil disalin.';
    } catch (copyError) {
      copyStatus.textContent = 'Clipboard tidak tersedia. Pilih teks hasil untuk menyalin secara manual.';
    }
  });
  downloadButton.addEventListener('click', () => {
    const blob = new Blob([`${output.textContent}\n`], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'hasil-aksara-jawa.txt';
    link.hidden = true;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.getElementById('increase-size').addEventListener('click', () => {
    outputSize = Math.min(MAX_SIZE, outputSize + 3);
    output.style.fontSize = `${outputSize}px`;
  });
  document.getElementById('result-font').addEventListener('change', (event) => {
    output.style.fontFamily = FONT_STACKS[event.currentTarget.value];
  });
  document.getElementById('theme-toggle').addEventListener('click', (event) => {
    const isDark = document.body.classList.toggle('dark-theme');
    event.currentTarget.setAttribute('aria-label', isDark ? 'Aktifkan tema terang' : 'Aktifkan tema gelap');
  });

  updateCount();
}(typeof window === 'undefined' ? globalThis : window));