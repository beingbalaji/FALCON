(function () {
  "use strict";

  // Dateline in the top bar.
  var today = document.querySelector("[data-today]");
  if (today) {
    today.textContent = new Date().toLocaleDateString("en-US", {
      weekday: "long", year: "numeric", month: "long", day: "numeric",
    });
  }

  // Claim / article tabs.
  function showTab(name) {
    document.querySelectorAll("[data-tab]").forEach(function (t) {
      var on = t.getAttribute("data-tab") === name;
      t.classList.toggle("on", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll("[data-panel]").forEach(function (p) {
      p.hidden = p.getAttribute("data-panel") !== name;
    });
  }
  document.querySelectorAll("[data-tab]").forEach(function (t) {
    t.addEventListener("click", function () { showTab(t.getAttribute("data-tab")); });
  });
  if (location.hash === "#article" && document.querySelector("[data-panel]")) showTab("article");
  document.querySelectorAll("[data-tab-link]").forEach(function (a) {
    a.addEventListener("click", function () {
      if (document.querySelector("[data-panel]")) setTimeout(function () { showTab("article"); }, 0);
    });
  });

  // Example chips fill the claim box.
  document.querySelectorAll("[data-example]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var box = document.getElementById("claim");
      box.value = chip.getAttribute("data-example");
      box.focus();
    });
  });

  // "On deadline" overlay while the server works.
  var press = document.getElementById("press");
  document.querySelectorAll("form[data-press]").forEach(function (form) {
    form.addEventListener("submit", function () {
      if (!press) return;
      press.hidden = false;
      var steps = press.querySelectorAll(".press-steps li");
      var i = 0;
      function tick() {
        steps.forEach(function (s, j) {
          s.classList.toggle("done", j < i);
          s.classList.toggle("now", j === i);
        });
        if (i < steps.length - 1) { i += 1; setTimeout(tick, 2600); }
      }
      tick();
    });
  });
  window.addEventListener("pageshow", function () { if (press) press.hidden = true; });

  // Copy link.
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(b.getAttribute("data-copy")).then(function () {
        var old = b.textContent; b.textContent = "Link copied";
        setTimeout(function () { b.textContent = old; }, 1600);
      });
    });
  });
})();
