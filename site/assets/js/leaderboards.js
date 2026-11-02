// Everything from the API goes in through textContent, so a player's name can never become markup.
(function () {
  var COUNT = 'count';
  var AMOUNT = 'amount';
  var BOARDS = {
    gcoin: {
      sortBy: 'balance',
      columns: [{ key: 'balance', label: 'GCoin', type: AMOUNT }]
    },
    storms: {
      sortBy: 'numStormWins',
      columns: [
        { key: 'numStormWins', label: 'Wins', type: COUNT },
        { key: 'numNetStormRewards', label: 'Net Rewards', type: AMOUNT },
        { key: 'numStormStarts', label: 'Starts', type: COUNT },
        { key: 'numStormTier1Multi', label: 'Single Guess', type: COUNT },
        { key: 'numStormTier2Multi', label: 'Two Guesses', type: COUNT },
        { key: 'numStormTier3Multi', label: 'Three Guesses', type: COUNT },
        { key: 'numStormTier4Multi', label: 'Four Guesses', type: COUNT }
      ]
    },
    whodis: {
      sortBy: 'numWhoDisWins',
      columns: [
        { key: 'numWhoDisWins', label: 'Wins', type: COUNT },
        { key: 'numWhoDisRewards', label: 'Total Rewards', type: AMOUNT }
      ]
    }
  };
  var MEDALS = ['🥇', '🥈', '🥉'];

  var root = document.getElementById('leaderboards');
  var tabs = Array.prototype.slice.call(root.querySelectorAll('.tab'));
  var panel = document.getElementById('board');
  var status = document.getElementById('board-status');
  var scroller = root.querySelector('.table-scroll');
  var table = root.querySelector('.board-table');
  var players = null;
  var current = 'gcoin';
  var sort = null;

  function value(player, column) {
    var raw = player[column.key];
    return raw === undefined || raw === null ? (column.type === AMOUNT ? '0.00' : '0') : String(raw);
  }

  function display(text) {
    // works on the stored string, so large amounts never lose digits to floating point
    return text.replace(/\B(?<!\.\d*)(?=(\d{3})+(?!\d))/g, ',');
  }

  function compare(a, b, column) {
    var difference = Number(value(a, column)) - Number(value(b, column));
    return difference || String(a.username || '').localeCompare(String(b.username || ''));
  }

  function cell(tag, text, className) {
    var element = document.createElement(tag);
    element.textContent = text;
    if (className) {
      element.className = className;
    }
    return element;
  }

  function header(column) {
    var th = document.createElement('th');
    th.scope = 'col';
    var active = sort.key === column.key;
    if (active) {
      th.setAttribute('aria-sort', sort.descending ? 'descending' : 'ascending');
    }
    var button = cell('button', column.label + (active ? (sort.descending ? ' ▾' : ' ▴') : ''));
    button.type = 'button';
    button.addEventListener('click', function () {
      sort = { key: column.key, descending: active ? !sort.descending : true };
      render();
      table.querySelector('th[aria-sort] button').focus();
    });
    th.appendChild(button);
    return th;
  }

  function render() {
    var columns = BOARDS[current].columns;
    var sortColumn = columns.filter(function (column) { return column.key === sort.key; })[0];
    var rows = players.slice().sort(function (a, b) {
      return sort.descending ? compare(b, a, sortColumn) : compare(a, b, sortColumn);
    });

    table.textContent = '';
    var head = table.createTHead().insertRow();
    head.appendChild(cell('th', '#', 'rank'));
    head.appendChild(cell('th', 'Player', 'player'));
    columns.forEach(function (column) { head.appendChild(header(column)); });

    var body = table.createTBody();
    rows.forEach(function (player, index) {
      var row = body.insertRow();
      row.appendChild(cell('td', MEDALS[index] || String(index + 1), 'rank'));
      row.appendChild(cell('td', player.username || 'Unknown player', 'player'));
      columns.forEach(function (column) { row.appendChild(cell('td', display(value(player, column)))); });
    });
    scroller.hidden = false;
  }

  function select(board, moveFocus) {
    current = board;
    sort = { key: BOARDS[board].sortBy, descending: true };
    tabs.forEach(function (tab) {
      var selected = tab.dataset.board === board;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected) {
        panel.setAttribute('aria-labelledby', tab.id);
        if (moveFocus) {
          tab.focus();
        }
      }
    });
    if (players && players.length) {
      render();
    }
  }

  tabs.forEach(function (tab, index) {
    tab.addEventListener('click', function () {
      history.replaceState(null, '', '#' + tab.dataset.board);
      select(tab.dataset.board);
    });
    tab.addEventListener('keydown', function (event) {
      var step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (step) {
        event.preventDefault();
        var next = tabs[(index + step + tabs.length) % tabs.length];
        history.replaceState(null, '', '#' + next.dataset.board);
        select(next.dataset.board, true);
      }
    });
  });

  function selectLinked() {
    var linked = location.hash.slice(1);
    select(Object.prototype.hasOwnProperty.call(BOARDS, linked) ? linked : 'gcoin');
  }

  window.addEventListener('hashchange', selectLinked);
  selectLinked();

  fetch(root.dataset.endpoint)
    .then(function (response) {
      if (!response.ok) {
        throw new Error('The leaderboard API answered ' + response.status);
      }
      return response.json();
    })
    .then(function (json) {
      players = Object.keys(json || {}).map(function (id) { return json[id]; });
      if (!players.length) {
        status.textContent = 'No players yet. Be the first!';
        return;
      }
      status.hidden = true;
      render();
    })
    .catch(function () {
      status.textContent = "The leaderboard can't be reached right now. Please try again in a little while.";
    });
})();
