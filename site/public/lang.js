// The root address: go to the site in the first of the browser's languages that the site has,
// else English. Loaded in the page head, so it runs before anything is drawn. Nothing is stored.
(function () {
  var SITE = ["el", "en"];
  var wanted = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || ""];
  var lang = "en";
  for (var i = 0; i < wanted.length; i++) {
    var l = String(wanted[i]).toLowerCase().split("-")[0];
    if (SITE.indexOf(l) >= 0) { lang = l; break; }
  }
  location.replace("/" + lang + "/");
})();
