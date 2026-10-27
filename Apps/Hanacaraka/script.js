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
  const CONSONANT_CHARS = new Set(Object.values(CONSONANTS));
  // Unicode signs are used so rendering and conjunct shaping stay with the user's font.
  const VOWELS = {
    a: '', i: '\uA9B6', u: '\uA9B8', e: '\uA9BC',
    'é': '\uA9BA', 'è': '\uA9BA', o: '\uA9BA\uA9B4'
  };

  const CODAS = { ng: '\uA981', r: '\uA982', h: '\uA983' };
  const PANGKON = '\uA9C0';
  const JAVANESE_DIGITS = ['\uA9D0', '\uA9D1', '\uA9D2', '\uA9D3', '\uA9D4', '\uA9D5', '\uA9D6', '\uA9D7', '\uA9D8', '\uA9D9'];
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
    return text.replace(/[a-zéè]+|\d+/giu, (token) => {
      if (/^\d+$/.test(token)) {
        return [...token].map((digit) => JAVANESE_DIGITS[Number(digit)]).join('');
      }
      return transliterateWord(token);
    });
  }

  function prepareInput(text, format) {
    return format === 'lowercase' ? text.toLocaleLowerCase('id') : text;
  }

  const DEFAULT_VISIBILITY_SETTINGS = { showLowercase: false, showTranslate: false };
  const SETTINGS_STORAGE_KEY = 'hanacaraka.visibility.v2';

  function readVisibilitySettings() {
    try {
      const saved = JSON.parse(window.localStorage.getItem(SETTINGS_STORAGE_KEY) || 'null');
      return {
        showLowercase: typeof saved?.showLowercase === 'boolean' ? saved.showLowercase : false,
        showTranslate: typeof saved?.showTranslate === 'boolean' ? saved.showTranslate : false
      };
    } catch (error) {
      return { ...DEFAULT_VISIBILITY_SETTINGS };
    }
  }

  function renderTransliteration(text) {
    output.replaceChildren();
    let pangkonCount = 0;
    for (const character of text) {
      output.appendChild(document.createTextNode(character));
      if (character === PANGKON) {
        pangkonCount += 1;
        if (pangkonCount === 2) {
          output.appendChild(document.createElement('wbr'));
          pangkonCount = 0;
        }
      } else if (!CONSONANT_CHARS.has(character)) {
        pangkonCount = 0;
      }
    }
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
  const letterFormatOptions = document.getElementById('letter-format-options');
  const translateButton = document.getElementById('translate-button');
  const showLowercaseOption = document.getElementById('show-lowercase-option');
  const showTranslateOption = document.getElementById('show-translate-option');
  const MIN_SIZE = 26;
  const MAX_SIZE = 58;
  const FONT_STACKS = {
    noto: '"Noto Sans Javanese", "Javanese Text", sans-serif',
    serif: 'serif',
    sans: 'sans-serif'
  };
  let visibilitySettings = readVisibilitySettings();
  let outputSize = 38;
  let debounceTimer;

  function selectedFormat() {
    if (!visibilitySettings.showLowercase) return 'preserve';
    return document.querySelector('input[name="letter-format"]:checked').value;
  }

  function saveVisibilitySettings() {
    try {
      window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(visibilitySettings));
    } catch (error) {
      // Settings remain active for this page session when storage is unavailable.
    }
  }

  function applyVisibilitySettings() {
    letterFormatOptions.hidden = !visibilitySettings.showLowercase;
    translateButton.hidden = !visibilitySettings.showTranslate;
    showLowercaseOption.checked = visibilitySettings.showLowercase;
    showTranslateOption.checked = visibilitySettings.showTranslate;
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
      output.replaceChildren();
      preview.textContent = '';
      caption.textContent = 'Hasil akan muncul di sini';
      copyButton.disabled = true;
      downloadButton.disabled = true;
      return;
    }

    renderTransliteration(transliterate(prepared));
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
    input.value = 'Aku bocah sing sregep banget. Tangi gasik rewangi ibuku nyapu. Terus aku kudu adus ésuk.';
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
  document.getElementById('decrease-size').addEventListener('click', () => {
    outputSize = Math.max(MIN_SIZE, outputSize - 3);
    output.style.fontSize = `${outputSize}px`;
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

  document.getElementById('settings-button').addEventListener('click', () => {
    document.getElementById('settings-dialog').showModal();
  });
  document.getElementById('close-settings').addEventListener('click', () => {
    document.getElementById('settings-dialog').close();
  });
  document.getElementById('settings-dialog').addEventListener('click', (event) => {
    if (event.target === event.currentTarget) event.currentTarget.close();
  });
  showLowercaseOption.addEventListener('change', () => {
    visibilitySettings.showLowercase = showLowercaseOption.checked;
    saveVisibilitySettings();
    applyVisibilitySettings();
    updateResult(false);
  });
  showTranslateOption.addEventListener('change', () => {
    visibilitySettings.showTranslate = showTranslateOption.checked;
    saveVisibilitySettings();
    applyVisibilitySettings();
  });
  document.getElementById('reset-settings').addEventListener('click', () => {
    visibilitySettings = { ...DEFAULT_VISIBILITY_SETTINGS };
    saveVisibilitySettings();
    document.querySelector('input[name="letter-format"][value="preserve"]').checked = true;
    document.getElementById('result-font').value = 'noto';
    output.style.fontFamily = FONT_STACKS.noto;
    outputSize = 38;
    output.style.fontSize = '';
    document.body.classList.remove('dark-theme');
    document.getElementById('theme-toggle').setAttribute('aria-label', 'Aktifkan tema gelap');
    applyVisibilitySettings();
    updateResult(false);
  });

  function setupEasterEgg() {
    const secretTrigger = document.getElementById('secret-trigger');
    const secretHint = document.getElementById('secret-hint');
    const eggPanel = document.getElementById('egg-panel');
    const eggIntro = document.getElementById('egg-intro');
    const gameBoard = document.getElementById('game-board');
    const gameDialog = document.getElementById('game-dialog');
    const gameCards = document.getElementById('luck-cards');
    const gameOutcome = document.getElementById('game-outcome');
    const outcomeTitle = document.getElementById('outcome-title');
    const outcomeCopy = document.getElementById('outcome-copy');
    const voucherCard = document.getElementById('voucher-card');
    const bowlIcon = document.getElementById('bowl-icon');
    const playAgain = document.getElementById('play-again');
    const targetScore = 7;
    const game = { player: 0, agent: 0, finished: false, playerCards: { pentol: 0, kuah: 0, sambal: 0 } };

    function updateScores() {
      document.getElementById('player-score').textContent = String(game.player);
      document.getElementById('agent-score').textContent = String(game.agent);
    }

    function playEffect(actor, card) {
      const other = actor === 'player' ? 'agent' : 'player';
      const actorName = actor === 'player' ? 'Kamu' : 'Asyrafu';
      let note;

      if (card === 'pentol') {
        game[actor] += 2;
        note = 'Pentol hijau membawa 2 poin. Mantap!';
      } else if (card === 'kuah') {
        const missChance = actor === 'agent' ? 0.1 : 0.3;
        if (Math.random() < missChance) {
          game[actor] = Math.max(0, game[actor] - 1);
          note = 'Kuahnya terlalu pedas: kehilangan 1 poin.';
        } else {
          game[actor] += 3;
          note = 'Kuah kejutan penuh hoki: mendapat 3 poin!';
        }
      } else {
        game[actor] += 1;
        if (game[other] > 0) {
          game[other] -= 1;
          note = 'Sambal siluman mencuri 1 poin lawan.';
        } else {
          note = 'Sambal siluman memberi 1 poin tambahan.';
        }
      }

      return `${actorName}: ${note}`;
    }

    function chooseAgentCard() {
      const repeatedCard = Object.entries(game.playerCards).sort((left, right) => right[1] - left[1])[0];
      if (repeatedCard[1] >= 2) {
        return repeatedCard[0] === 'kuah' ? 'pentol' : 'kuah';
      }
      if (game.agent < targetScore - 3 || game.agent <= game.player) return 'kuah';
      if (game.player > 0) return 'sambal';
      return 'pentol';
    }

    function endGame(playerWon) {
      game.finished = true;
      gameCards.hidden = true;
      gameOutcome.hidden = false;
      playAgain.hidden = false;
      bowlIcon.hidden = !playerWon;
      voucherCard.hidden = !playerWon;
      if (playerWon) {
        outcomeTitle.textContent = 'SELAMAT! KAMU MENANG MELAWAN ASYRAFU!';
        outcomeCopy.textContent = 'Mustahil! Rencana bakso rahasiaku gagal. Voucher rahasia ini milikmu, agen!';
      } else {
        outcomeTitle.textContent = 'ASYRAFU MENANG DULUAN!';
        outcomeCopy.textContent = 'Haha, langkah kuahku lebih licin! Tenang, agen, misi berikutnya masih menunggu.';
      }
    }

    function startGame() {
      game.player = 0;
      game.agent = 0;
      game.finished = false;
      game.playerCards = { pentol: 0, kuah: 0, sambal: 0 };
      updateScores();
      eggIntro.hidden = true;
      gameBoard.hidden = false;
      gameCards.hidden = false;
      gameOutcome.hidden = true;
      playAgain.hidden = true;
      gameDialog.textContent = 'Kau cukup beruntung, tetapi bisakah menandingi agen Rusia? Pilih satu kartu.';
      gameCards.querySelector('button').focus();
    }

    function takeTurn(card) {
      if (game.finished) return;
      game.playerCards[card] += 1;
      const playerMessage = playEffect('player', card);
      updateScores();
      if (game.player >= targetScore) {
        gameDialog.textContent = playerMessage;
        endGame(true);
        return;
      }

      const agentCard = chooseAgentCard();
      const agentMessage = playEffect('agent', agentCard);
      updateScores();
      gameBoard.classList.remove('card-flash');
      void gameBoard.offsetWidth;
      gameBoard.classList.add('card-flash');
      gameDialog.textContent = `${playerMessage} ${agentMessage}`;
      if (game.agent >= targetScore) endGame(false);
    }

    secretTrigger.addEventListener('click', () => {
      const count = Number(secretTrigger.dataset.count || 0) + 1;
      secretTrigger.dataset.count = String(count);
      if (count < 5) {
        secretHint.textContent = `Sinyal belum lengkap (${count}/5).`;
        return;
      }
      secretTrigger.disabled = true;
      secretHint.textContent = 'Sinyal rahasia terbuka.';
      eggPanel.hidden = false;
      eggPanel.focus();
      eggPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
    document.getElementById('start-game').addEventListener('click', startGame);
    gameCards.querySelectorAll('.luck-card').forEach((button) => {
      button.addEventListener('click', () => takeTurn(button.dataset.card));
    });
    playAgain.addEventListener('click', startGame);
  }

  applyVisibilitySettings();
  setupEasterEgg();

  updateCount();
}(typeof window === 'undefined' ? globalThis : window));