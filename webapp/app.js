const telegram = window.Telegram?.WebApp;
const statusElement = document.querySelector('#status');
const searchInput = document.querySelector('#search-query');

function setStatus(message) {
  statusElement.textContent = message;
}

function sendToBot(payload) {
  if (!telegram || typeof telegram.sendData !== 'function') {
    setStatus('Откройте Mini App кнопкой внутри чата с ботом.');
    return;
  }

  telegram.HapticFeedback?.impactOccurred('light');
  setStatus('Отправляю запрос боту…');
  telegram.sendData(JSON.stringify(payload));
}

if (telegram) {
  telegram.ready();
  telegram.expand();
  telegram.setHeaderColor?.('secondary_bg_color');
  telegram.setBackgroundColor?.('bg_color');
} else {
  setStatus('Предпросмотр: отправка доступна только внутри Telegram.');
}

document.querySelector('#search-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const query = searchInput.value.trim();
  if (!query) {
    setStatus('Введите название трека или исполнителя.');
    searchInput.focus();
    return;
  }
  sendToBot({ action: 'search', query });
});

document.querySelector('#subscribe-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const artistInput = document.querySelector('#artist-name');
  const artist = artistInput.value.trim();
  if (!artist) {
    setStatus('Введите имя исполнителя.');
    artistInput.focus();
    return;
  }
  sendToBot({ action: 'subscribe_artist', artist });
});

document.querySelectorAll('[data-query]').forEach((button) => {
  button.addEventListener('click', () => {
    searchInput.value = button.dataset.query;
    searchInput.focus();
  });
});
