// Market Terminal – kleine Helfer im Browser

// 1) Zeitraum-Knöpfe über den Charts (1M, 3M, 6M, YTD, 1J, 2J)
document.querySelectorAll(".zeitraum").forEach(function (gruppe) {
  gruppe.addEventListener("click", function (e) {
    var knopf = e.target.closest("button");
    var gd = document.getElementById(gruppe.dataset.chart);
    if (!knopf || !gd || !gd.data) return;
    gruppe.querySelectorAll("button").forEach(function (b) { b.classList.toggle("aktiv", b === knopf); });

    var ende = "";
    gd.data.forEach(function (t) { var x = t.x[t.x.length - 1]; if (x > ende) ende = x; });
    var endeDatum = new Date(ende + "T00:00:00Z");
    var start = knopf.dataset.tage === "ytd"
      ? new Date(Date.UTC(endeDatum.getUTCFullYear() - 1, 11, 31))
      : new Date(endeDatum.getTime() - Number(knopf.dataset.tage) * 864e5);
    var s = start.toISOString().slice(0, 10);

    var tief = Infinity, hoch = -Infinity;
    gd.data.forEach(function (t) {
      for (var i = 0; i < t.x.length; i++) {
        if (t.x[i] >= s && t.y[i] !== null) { tief = Math.min(tief, t.y[i]); hoch = Math.max(hoch, t.y[i]); }
      }
    });
    var puffer = (hoch - tief) * 0.08 || Math.abs(hoch) * 0.02 || 1;
    var bis = new Date(endeDatum.getTime() + 2 * 864e5).toISOString().slice(0, 10);
    Plotly.relayout(gd, { "xaxis.range": [s, bis], "yaxis.range": [tief - puffer, hoch + puffer] });
  });
});

// 2) Filter auf der News-Seite
document.querySelectorAll(".filter").forEach(function (leiste) {
  leiste.addEventListener("click", function (e) {
    var knopf = e.target.closest("button");
    if (!knopf) return;
    leiste.querySelectorAll("button").forEach(function (b) { b.classList.toggle("aktiv", b === knopf); });
    var wahl = knopf.dataset.filter;
    document.querySelectorAll("[data-thema]").forEach(function (el) {
      el.hidden = wahl !== "alle" && el.dataset.thema !== wahl;
    });
  });
});

// 3) Reiter (Märkte, Makro, Themen): immer nur einen Bereich zeigen.
//    Die Adresse merkt sich den Reiter (z. B. themen.html#hormuz), damit Links direkt dorthin führen.
document.querySelectorAll("[data-reiter]").forEach(function (leiste) {
  var knoepfe = Array.prototype.slice.call(leiste.querySelectorAll("button"));
  var bereiche = Array.prototype.slice.call(document.querySelectorAll(".reiter-inhalt"));

  function zeige(ziel, scrollen) {
    if (!knoepfe.some(function (b) { return b.dataset.ziel === ziel; })) ziel = knoepfe[0].dataset.ziel;
    knoepfe.forEach(function (b) { b.classList.toggle("aktiv", b.dataset.ziel === ziel); });
    bereiche.forEach(function (bereich) {
      var sichtbar = bereich.dataset.id === ziel;
      bereich.hidden = !sichtbar;
      // Charts, die versteckt gezeichnet wurden, an die richtige Breite anpassen
      if (sichtbar && window.Plotly) bereich.querySelectorAll(".js-plotly-plot").forEach(function (gd) { Plotly.Plots.resize(gd); });
    });
    if (scrollen) leiste.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  leiste.addEventListener("click", function (e) {
    var knopf = e.target.closest("button");
    if (!knopf) return;
    history.replaceState(null, "", "#" + knopf.dataset.ziel);
    zeige(knopf.dataset.ziel, false);
  });
  window.addEventListener("hashchange", function () { zeige(location.hash.slice(1), true); });
  zeige(location.hash.slice(1) || (leiste.querySelector(".aktiv") || knoepfe[0]).dataset.ziel, !!location.hash);
});
