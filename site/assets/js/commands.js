// The list works without this file: it only adds the search box and opens linked commands.
(function () {
  var search = document.getElementById('command-search');
  var empty = document.getElementById('command-empty');
  var groups = Array.prototype.slice.call(document.querySelectorAll('.command-group'));

  function filter() {
    var query = search.value.trim().toLowerCase();
    var anyShown = false;
    groups.forEach(function (group) {
      var groupShown = false;
      group.querySelectorAll('.command').forEach(function (command) {
        var shown = command.textContent.toLowerCase().indexOf(query) !== -1;
        command.hidden = !shown;
        groupShown = groupShown || shown;
      });
      group.hidden = !groupShown;
      anyShown = anyShown || groupShown;
    });
    empty.hidden = anyShown;
  }

  function openLinkedCommand() {
    var target = location.hash ? document.getElementById(location.hash.slice(1)) : null;
    if (target && target.tagName === 'DETAILS') {
      target.open = true;
      target.scrollIntoView();
    }
  }

  search.hidden = false;
  search.addEventListener('input', filter);
  window.addEventListener('hashchange', openLinkedCommand);
  openLinkedCommand();
})();
