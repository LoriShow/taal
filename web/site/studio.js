/* Taal Studio: a parent describes a song; the worker writes words and a tune; the draft
   plays straight away in the main player with a bell and a beat click. */
(function () {
  "use strict";
  var CFG = window.TAAL;
  var $ = function (id) { return document.getElementById(id); };
  if (!$("studio") || !window.supabase) return;
  var sb = window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseKey);
  var CODE_KEY = "taal-studio-code", LAST_KEY = "taal-studio-last";
  var code = null, current = null, lastBrief = null, polling = 0;

  function store(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function status(t) { $("st-status").textContent = t || ""; }

  function open(c) {
    code = c; store(CODE_KEY, c);
    $("studio-locked").hidden = true; $("studio-open").hidden = false;
    var last = read(LAST_KEY);
    if (last) watch(last, true);
  }
  $("studio-code-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var c = $("studio-code").value.trim();
    if (c) open(c);
  });
  var saved = read(CODE_KEY);
  if (saved) open(saved);

  function brief(variation) {
    var mood = document.querySelector('input[name="st-mood"]:checked');
    var level = document.querySelector('input[name="st-level"]:checked');
    return {
      about: $("st-about").value.trim(),
      child_name: $("st-name").value.trim(),
      mood: mood ? mood.value : "bouncy",
      level: level ? Number(level.value) : 1,
      variation: variation || 0
    };
  }

  function request(b) {
    lastBrief = b;
    $("st-write").disabled = true; $("st-again").disabled = true;
    status("Writing your song… about 20 seconds.");
    sb.rpc("taal_studio_request", { code: code, brief: b }).then(function (res) {
      if (res.error) {
        $("st-write").disabled = false; $("st-again").disabled = false;
        if (/unknown studio code/i.test(res.error.message)) {
          store(CODE_KEY, null); $("studio-open").hidden = true; $("studio-locked").hidden = false;
          status(""); alertCode();
        } else status("Couldn't start: " + res.error.message);
        return;
      }
      store(LAST_KEY, res.data);
      watch(res.data, false);
    });
  }
  function alertCode() { $("studio-code").value = ""; $("studio-code").placeholder = "That code didn't work. Try again."; }

  function watch(id, quiet) {
    var mine = ++polling, tries = 0;
    (function tick() {
      if (mine !== polling) return;
      sb.rpc("taal_studio_get", { code: code, draft_id: id }).then(function (res) {
        if (mine !== polling) return;
        var d = res.data;
        if (res.error || !d) { if (!quiet) status("Couldn't find that draft."); done(); return; }
        if (d.status === "ready") { done(); status(""); show(d); return; }
        if (d.status === "failed") { done(); status("That one didn't work out. Press “Write my song” to try again."); return; }
        if (++tries > 90) { done(); status("This is taking too long. Try again in a minute."); return; }
        if (!quiet) status(d.status === "writing" ? "Writing your song… checking the tune is easy to play." : "Writing your song… about 20 seconds.");
        setTimeout(tick, 2000);
      });
    })();
  }
  function done() { $("st-write").disabled = false; $("st-again").disabled = false; }

  function show(d) {
    current = d;
    if (d.brief) {
      lastBrief = d.brief;
      if (!$("st-about").value) $("st-about").value = d.brief.about || "";
      if (!$("st-name").value) $("st-name").value = d.brief.child_name || "";
    }
    var song = d.draft;
    $("st-title").textContent = song.title;
    var secs = song.plan.sections;
    $("st-listen").value = (secs[1].lines || []).join("\n");
    $("st-together").value = (secs[3].lines || []).join("\n");
    var roll = $("st-roll"); roll.textContent = "";
    roll.style.setProperty("--beats", 16);
    for (var b = 0; b < 16; b++) {
      var c = document.createElement("div");
      c.className = "cell" + (b % 4 === 0 && b > 0 ? " bar" : "");
      var n = song.tune.notes.filter(function (x) { return x.start === b; })[0];
      if (n) { c.setAttribute("data-n", n.pitch[0]); c.textContent = n.pitch[0]; }
      roll.appendChild(c);
    }
    $("st-draft").hidden = false;
  }

  function lines(id) {
    return $(id).value.split("\n").map(function (x) { return x.trim().slice(0, 40); }).filter(Boolean).slice(0, 4);
  }
  $("st-hear").addEventListener("click", function () {
    if (!current || !window.TaalPlayer) return;
    var song = JSON.parse(JSON.stringify(current.draft));
    song.plan.sections[1].lines = lines("st-listen");
    song.plan.sections[3].lines = lines("st-together");
    window.TaalPlayer.load({
      id: "draft-" + current.id, title: song.title, level: song.level, tune: song.tune, plan: song.plan,
      sample_audio_path: null, draft: true
    });
    var p = document.querySelector(".player");
    if (p) p.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("studio-form").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!$("st-about").value.trim()) return;
    request(brief(0));
  });
  $("st-again").addEventListener("click", function () {
    var b = lastBrief || brief(0);
    b = JSON.parse(JSON.stringify(b)); b.variation = (b.variation || 0) + 1;
    request(b);
  });
})();
