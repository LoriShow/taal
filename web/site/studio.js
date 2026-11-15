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
    loadSongs();
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
        if (d.status === "ready") {
          done(); status(""); show(d);
          var mk = (d.draft && d.draft.make) || {}, vd = (d.draft && d.draft.video) || {};
          if (mk.status === "queued" || vd.status === "queued") follow(d.id);
          return;
        }
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
    showMake(d);
  }

  /* ---- Step 2: real music, video, and the family's songs ---- */
  function pub(path) { return CFG.supabaseUrl + "/storage/v1/object/public/taal-public/" + path; }
  function makeStatus(t) { $("st-make-status").textContent = t; }
  function showMake(d) {
    var song = d.draft || {}, make = song.make || {}, video = song.video || {};
    $("st-make").hidden = make.status === "made";
    $("st-make").disabled = make.status === "queued";
    $("st-video").hidden = make.status !== "made" || video.status === "made";
    $("st-video").disabled = video.status === "queued";
    $("st-video-link").hidden = video.status !== "made";
    if (video.status === "made") $("st-video-link").href = pub(video.path);
    if (make.status === "queued") makeStatus("Making your song with real music… about a minute.");
    else if (make.status === "failed") { makeStatus("The music didn't work this time. Press “Make it” to try again."); $("st-make").hidden = false; }
    else if (make.status === "made") makeStatus(video.status === "queued" ? "Making the play-along video… about half a minute." :
      video.status === "failed" ? "The video didn't work this time; try again." :
      "Done! “Hear it in the player” now plays the real music. It's saved under Our songs.");
    else makeStatus("Takes about a minute. The words are sent to our music maker, so use only what you're happy to share.");
  }
  function follow(id) {
    var mine = ++polling, tries = 0;
    (function tick() {
      if (mine !== polling) return;
      sb.rpc("taal_studio_get", { code: code, draft_id: id }).then(function (res) {
        if (mine !== polling || res.error || !res.data) return;
        current = res.data; showMake(res.data);
        var song = res.data.draft || {}, make = song.make || {}, video = song.video || {};
        if (make.status === "made" && video.status !== "queued") { loadSongs(); return; }
        if (make.status === "failed") return;
        if (++tries > 120) { makeStatus("This is taking longer than usual. Check Our songs in a few minutes."); return; }
        setTimeout(tick, 3000);
      });
    })();
  }
  $("st-make").addEventListener("click", function () {
    if (!current) return;
    $("st-make").disabled = true;
    makeStatus("Starting…");
    sb.rpc("taal_studio_make", { code: code, draft_id: current.id,
      words: { listen: lines("st-listen"), together: lines("st-together") } }).then(function (res) {
      if (res.error) { $("st-make").disabled = false; makeStatus("Couldn't start: " + res.error.message); return; }
      follow(current.id);
    });
  });
  $("st-video").addEventListener("click", function () {
    if (!current) return;
    $("st-video").disabled = true;
    sb.rpc("taal_studio_video", { code: code, draft_id: current.id }).then(function (res) {
      if (res.error) { $("st-video").disabled = false; makeStatus("Couldn't start the video: " + res.error.message); return; }
      follow(current.id);
    });
  });
  function loadSongs() {
    sb.rpc("taal_studio_list", { code: code }).then(function (res) {
      var list = (res && res.data) || [];
      var ol = $("st-song-list"); ol.textContent = "";
      $("st-songs").hidden = !list.length;
      list.forEach(function (it) {
        var li = document.createElement("li");
        var b = document.createElement("b"); b.textContent = it.title || "Our song"; li.appendChild(b);
        var row = document.createElement("span"); row.className = "row";
        var play = document.createElement("button"); play.className = "btn primary"; play.type = "button"; play.textContent = "Play";
        play.addEventListener("click", function () { openSong(it.id); });
        row.appendChild(play);
        if (it.video && it.video.status === "made") {
          var a = document.createElement("a"); a.className = "btn"; a.textContent = "Video"; a.target = "_blank"; a.rel = "noopener";
          a.href = pub(it.video.path); row.appendChild(a);
        }
        li.appendChild(row); ol.appendChild(li);
      });
    });
  }
  function openSong(id) {
    sb.rpc("taal_studio_get", { code: code, draft_id: id }).then(function (res) {
      if (res.error || !res.data) return;
      store(LAST_KEY, id); show(res.data); hear();
    });
  }

  function lines(id) {
    return $(id).value.split("\n").map(function (x) { return x.trim().slice(0, 40); }).filter(Boolean).slice(0, 4);
  }
  $("st-hear").addEventListener("click", function () { hear(); });
  function hear() {
    if (!current || !window.TaalPlayer) return;
    var song = JSON.parse(JSON.stringify(current.draft));
    var made = song.make && song.make.status === "made";
    if (!made) {
      song.plan.sections[1].lines = lines("st-listen");
      song.plan.sections[3].lines = lines("st-together");
    }
    window.TaalPlayer.load({
      id: "draft-" + current.id, title: song.title, level: song.level, tune: song.tune, plan: song.plan,
      sample_audio_path: made ? song.make.audio_path : null, draft: !made
    });
    var p = document.querySelector(".player");
    if (p) p.scrollIntoView({ behavior: "smooth", block: "start" });
  }
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
