/* Taal site: the song player, and the family area (sign-in, links, instrument photos). */
(function () {
  "use strict";
  var CFG = window.TAAL;
  var $ = function (id) { return document.getElementById(id); };
  var sb = null;
  try { sb = window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseKey); } catch (e) { sb = null; }

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }

  /* ---------- Player ---------- */

  var SEMI = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  function midi(p) {
    var m = /^([A-Ga-g])([#b]*)(-?\d+)$/.exec(p);
    if (!m) return 60;
    var off = 0;
    for (var i = 0; i < m[2].length; i++) off += m[2][i] === "#" ? 1 : -1;
    return 12 * (parseInt(m[3], 10) + 1) + SEMI[m[1].toUpperCase()] + off;
  }
  function hz(p) { return 440 * Math.pow(2, (midi(p) - 69) / 12); }
  function letter(p) { return p[0].toUpperCase(); }

  var P = { ctx: null, gain: null, startCtx: 0, playing: false, raf: 0, audio: null };
  var ALBUM = [], albumMode = false;
  var song = null, SECTIONS = [], NOTES = [], TOTAL = 0, BEAT = 0, PER_BAR = 4, tuneBeats = 16, keyEls = {}, cells = [];

  function setupSong(s) {
    song = s;
    var bpm = s.tune.bpm; BEAT = 60 / bpm; PER_BAR = s.tune.beats_per_bar || 4;
    var last = 0;
    s.tune.notes.forEach(function (n) { last = Math.max(last, n.start + n.length); });
    tuneBeats = Math.ceil(last / PER_BAR) * PER_BAR;

    var bar = 0; SECTIONS = []; NOTES = [];
    s.plan.sections.forEach(function (sec, si) {
      var o = { name: sec.name, bars: sec.bars, kind: sec.kind || "listen", start: bar * PER_BAR * BEAT, lines: sec.lines || [] };
      bar += sec.bars; o.end = bar * PER_BAR * BEAT;
      o.tune = sec.bars * PER_BAR >= tuneBeats;
      o.say = o.kind === "turn" ? "Your turn!" : (o.tune ? (/together/i.test(o.name) ? "Play together" : "Listen and watch") : "Listen");
      SECTIONS.push(o);
      if (o.tune) s.tune.notes.forEach(function (n) {
        NOTES.push({ p: n.pitch, t: o.start + n.start * BEAT, turn: o.kind === "turn", hit: false });
      });
    });
    TOTAL = bar * PER_BAR * BEAT;

    $("song-title").textContent = s.title || "A Taal song";
    $("song-eyebrow").textContent = (s.track ? "Song " + s.track + " · " : "") + "Level " + (s.level || 1);
    Array.prototype.forEach.call(document.querySelectorAll("#tracks button"), function (b) {
      b.setAttribute("aria-current", b.dataset.id === s.id ? "true" : "false");
    });
    var timeline = $("timeline"), head = $("head");
    Array.prototype.slice.call(timeline.querySelectorAll(".sec")).forEach(function (n) { n.remove(); });
    SECTIONS.forEach(function (o) {
      var d = el("div", { "class": "sec" + (o.kind === "turn" ? " turn" : "") });
      d.style.setProperty("--bars", o.bars);
      d.appendChild(document.createTextNode(o.name));
      d.appendChild(el("small", {}, o.bars + " bars"));
      timeline.insertBefore(d, head); o.el = d;
    });

    var roll = $("roll"); roll.textContent = ""; cells = [];
    roll.style.setProperty("--beats", tuneBeats);
    for (var b = 0; b < tuneBeats; b++) {
      var c = el("div", { "class": "cell" + (b % PER_BAR === 0 && b > 0 ? " bar" : "") });
      var n = s.tune.notes.filter(function (x) { return x.start === b; })[0];
      if (n) { c.setAttribute("data-n", letter(n.pitch)); c.textContent = letter(n.pitch); }
      roll.appendChild(c); cells.push(c);
    }

    var keys = $("keys"); keys.textContent = ""; keyEls = {};
    var pitches = [];
    s.tune.notes.forEach(function (n) { if (pitches.indexOf(n.pitch) < 0) pitches.push(n.pitch); });
    pitches.sort(function (a, b) { return midi(a) - midi(b); });
    pitches.forEach(function (p, i) {
      var k = el("button", { "class": "key", type: "button", "data-n": letter(p), "aria-label": "Play " + letter(p) });
      k.appendChild(document.createTextNode(letter(p)));
      k.appendChild(el("small", {}, "key " + (i + 1)));
      k.addEventListener("pointerdown", function (e) { e.preventDefault(); tap(p); });
      k.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tap(p); } });
      keys.appendChild(k); keyEls[p] = k;
    });
    P.pitches = pitches;
    var dots = $("dots"); dots.textContent = ""; P.dotEls = {};
    pitches.forEach(function (p) { var d = el("i", { "data-n": letter(p) }); dots.appendChild(d); P.dotEls[p] = d; });

    if (s.sample_audio_path) {
      P.audio = new Audio(CFG.supabaseUrl + "/storage/v1/object/public/taal-public/" + s.sample_audio_path);
      P.audio.preload = "auto";
      P.audio.addEventListener("error", function () {
        P.audio = null;
        $("audiostate").textContent = "The backing track could not load, so you'll hear a click on each beat and the notes.";
      });
    } else {
      P.audio = null;
      $("audiostate").textContent = "This song has no backing track yet: you'll hear a click on each beat and the notes.";
    }
    draw(0, true);
  }

  function ensureCtx() {
    if (!P.ctx) { var AC = window.AudioContext || window.webkitAudioContext; if (AC) P.ctx = new AC(); }
    if (P.ctx && P.ctx.state === "suspended") P.ctx.resume().catch(function () {});
    return P.ctx;
  }
  function tone(p, when, dest, vol) {
    var ctx = P.ctx; if (!ctx) return;
    var g = ctx.createGain(); g.connect(dest || ctx.destination);
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(vol || 0.5, when + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.7);
    [[1, 1], [4, 0.25]].forEach(function (h) {
      var o = ctx.createOscillator(), og = ctx.createGain();
      o.frequency.value = hz(p) * h[0]; og.gain.value = h[1];
      o.connect(og); og.connect(g); o.start(when); o.stop(when + 0.75);
    });
  }
  function click(when, strong, dest) {
    var ctx = P.ctx, o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = strong ? 1200 : 800;
    g.gain.setValueAtTime(strong ? 0.12 : 0.06, when);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.05);
    o.connect(g); g.connect(dest); o.start(when); o.stop(when + 0.06);
  }
  function now() {
    if (P.audio && !P.audio.paused) return P.audio.currentTime;
    return P.ctx ? P.ctx.currentTime - P.startCtx : 0;
  }
  function start() {
    if (!ensureCtx()) { $("score").textContent = "This browser cannot play sound here."; return; }
    NOTES.forEach(function (n) { n.hit = false; });
    filmHide();
    P.gain = P.ctx.createGain(); P.gain.connect(P.ctx.destination);
    P.startCtx = P.ctx.currentTime + (P.audio ? 0 : 0.12);
    NOTES.forEach(function (n) { if (!n.turn) tone(n.p, P.startCtx + n.t, P.gain, 0.45); });
    if (P.audio) {
      P.audio.currentTime = 0;
      P.audio.play().catch(function () { $("score").textContent = "The music could not start. Press Play again."; });
    } else {
      for (var i = 0; i < Math.round(TOTAL / BEAT); i++) click(P.startCtx + i * BEAT, i % PER_BAR === 0, P.gain);
    }
    P.playing = true; $("playbtn").textContent = "Stop";
    $("score").textContent = "Listen first. Your turn comes after the first tune.";
    P.raf = requestAnimationFrame(frame);
  }
  function stop(finished) {
    P.playing = false; $("playbtn").textContent = "Play";
    cancelAnimationFrame(P.raf);
    if (P.gain) { try { P.gain.disconnect(); } catch (e) {} P.gain = null; }
    if (P.audio) P.audio.pause();
    $("score").textContent = "On a computer, the number keys play the notes too.";
    if (finished) {
      var turn = NOTES.filter(function (n) { return n.turn; });
      var got = turn.filter(function (n) { return n.hit; }).length;
      $("score").textContent = "You caught " + got + " of " + turn.length + " notes in your turn. " +
        (got >= turn.length * 0.75 ? "Lovely playing!" : "Play again and tap as each key lights up.");
    }
    draw(0, true);
    if (finished && albumMode) {
      var i = ALBUM.map(function (x) { return x.id; }).indexOf(song.id);
      if (i >= 0 && i + 1 < ALBUM.length) { setupSong(ALBUM[i + 1]); start(); return; }
    }
    if (albumMode) { albumMode = false; $("playall").textContent = "Play the whole album"; }
    if (finished) filmCheer(); else filmHide();
  }
  function fmt(t) { var s = Math.max(0, Math.floor(t)); return Math.floor(s / 60) + ":" + (s % 60 < 10 ? "0" : "") + (s % 60); }
  function draw(t, idle) {
    $("head").style.left = (100 * Math.min(t, TOTAL) / TOTAL) + "%";
    $("clock").textContent = fmt(t) + " / " + fmt(TOTAL);
    var cur = null;
    SECTIONS.forEach(function (s) { var on = !idle && t >= s.start && t < s.end; s.el.classList.toggle("active", on); if (on) cur = s; });
    $("now").textContent = idle ? "Ready" : (cur ? cur.say : "");
    $("now").classList.toggle("turn", !!cur && cur.kind === "turn");
    var words = idle || !cur ? "" : (cur.kind === "turn" ? "Tap the keys as they light up." : cur.lines.join("\n"));
    if ($("lyrics").textContent !== words) $("lyrics").textContent = words;
    $("beat").classList.toggle("on", !idle && (t / BEAT - Math.floor(t / BEAT)) < 0.25);
    var inTune = cur && cur.tune ? Math.floor((t - cur.start) / BEAT) : -1;
    cells.forEach(function (c, i) { c.classList.toggle("now", i === inTune); });
    var due = {};
    if (!idle) NOTES.forEach(function (n) { if (t >= n.t - 0.05 && t < n.t + BEAT * 0.8) due[n.p] = true; });
    Object.keys(keyEls).forEach(function (p) {
      keyEls[p].classList.toggle("due", !!due[p]);
      if (P.dotEls && P.dotEls[p]) P.dotEls[p].classList.toggle("on", !!due[p]);
    });
    var onBeat = !idle && (t / BEAT - Math.floor(t / BEAT)) < 0.3;
    $("hopper").classList.toggle("hop", onBeat);
    if (STAGE.drum) STAGE.drum.classList.toggle("hop", onBeat);
    STAGE.friends.forEach(function (f, i) {
      var playing = false;
      (P.pitches || []).forEach(function (p, pi) { if (due[p] && pi % STAGE.friends.length === i) playing = true; });
      f.classList.toggle("play", playing);
      f.classList.toggle("hop", onBeat && !playing);
    });
    $("stage").classList.toggle("turn", !!cur && cur.kind === "turn");
  }
  function frame() {
    if (!P.playing) return;
    var t = now();
    if (t >= TOTAL || (P.audio && P.audio.ended)) { stop(true); return; }
    draw(Math.max(0, t), false);
    P.raf = requestAnimationFrame(frame);
  }
  function tap(p) {
    ensureCtx();
    if (P.ctx) tone(p, P.ctx.currentTime, null, 0.6);
    var k = keyEls[p]; if (!k) return;
    k.classList.add("down"); setTimeout(function () { k.classList.remove("down"); }, 140);
    if (!P.playing) return;
    var t = now();
    for (var i = 0; i < NOTES.length; i++) {
      var n = NOTES[i];
      if (n.turn && !n.hit && n.p === p && Math.abs(t - n.t) < 0.3) { n.hit = true; break; }
    }
  }
  document.addEventListener("keydown", function (e) {
    if (e.repeat || /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
    var i = parseInt(e.key, 10);
    if (i >= 1 && P.pitches && P.pitches[i - 1]) tap(P.pitches[i - 1]);
  });
  $("playbtn").addEventListener("click", function () {
    if (P.playing) { albumMode = false; stop(false); } else start();
  });
  $("playall").addEventListener("click", function () {
    if (albumMode) { albumMode = false; stop(false); return; }
    if (P.playing) stop(false);
    if (ALBUM.length) setupSong(ALBUM[0]);
    albumMode = true; $("playall").textContent = "Stop the album";
    start();
  });

  /* The themed stage. Every piece is optional: whatever fails to load is simply left out. */
  var STAGE = { drum: null, friends: [] };
  function pub(path) { return CFG.supabaseUrl + "/storage/v1/object/public/taal-public/" + path; }
  var FILM = null;
  // A cast is a still picture of the child's chosen band. Nothing moves while the song plays,
  // so the keys keep the child's eyes. One short clip of the band plays once as a reward at the end.
  function loadCast(cast) {
    var stageEl = $("stage");
    Array.prototype.slice.call(stageEl.querySelectorAll("video.film")).forEach(function (v) { v.pause(); v.remove(); });
    FILM = { id: cast.id, cheer: null };
    stageEl.style.backgroundImage = "url(" + pub(cast.poster) + ")";
    stageEl.classList.remove("has-cover"); stageEl.classList.add("still"); STAGE.backdrop = true;
    $("hopper").style.display = "none";
    var path = cast.clips && (cast.clips.outro || cast.clips.together || cast.clips.play);
    if (path) {
      var film = FILM, v = document.createElement("video");
      v.className = "stagevid film"; v.muted = true; v.loop = false; v.playsInline = true; v.preload = "metadata";
      v.setAttribute("playsinline", ""); v.style.opacity = "0";
      v.addEventListener("ended", function () { v.style.opacity = "0"; });
      v.src = pub(path);
      stageEl.insertBefore(v, stageEl.firstChild);
      film.cheer = v;
    }
    Array.prototype.forEach.call(document.querySelectorAll("#casts button"), function (b) {
      b.setAttribute("aria-pressed", b.dataset.id === cast.id ? "true" : "false");
    });
    try { localStorage.setItem("taal-cast", cast.id); } catch (e) {}
  }
  function filmHide() {
    if (FILM && FILM.cheer) { FILM.cheer.pause(); FILM.cheer.style.opacity = "0"; }
  }
  function filmCheer() {
    if (!FILM || !FILM.cheer) return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var v = FILM.cheer;
    try { v.currentTime = 0; } catch (e) {}
    v.play().then(function () { v.style.opacity = "1"; }).catch(function () {});
  }
  // Pictures on the player are switched off: the keys are the only thing to watch.
  if (CFG.stage === false) { $("stage").style.display = "none"; $("castbar").style.display = "none"; }
  if (CFG.stage !== false && CFG.casts && CFG.casts.length) {
    var bar = $("casts"), saved = null;
    try { saved = localStorage.getItem("taal-cast"); } catch (e) {}
    CFG.casts.forEach(function (cast) {
      var b = el("button", { type: "button", "data-id": cast.id, "aria-pressed": "false" });
      var im = el("img", { alt: "", width: "96", height: "54", loading: "lazy" });
      im.src = pub(cast.poster);
      b.appendChild(im); b.appendChild(el("span", {}, cast.name));
      b.addEventListener("click", function () { loadCast(cast); });
      bar.appendChild(b);
    });
    $("castbar").hidden = false;
    loadCast(CFG.casts.filter(function (c) { return c.id === saved; })[0] || CFG.casts[0]);
  }
  if (CFG.stage !== false && CFG.theme && !(CFG.casts && CFG.casts.length)) {
    var cast = $("cast"), spots = [["24%", "27%", "17%"], ["76%", "27%", "17%"], ["62%", "58%", "11%"]];
    var addChar = function (path, cls, x, b, w, done) {
      var im = new Image();
      im.className = "char " + cls; im.alt = "";
      im.style.setProperty("--x", x); im.style.setProperty("--b", b); im.style.setProperty("--w", w);
      im.onload = function () { cast.appendChild(im); done(im); };
      im.src = pub(path);
    };
    addChar(CFG.theme.drum, "drum", "50%", "27%", "19%", function (im) { STAGE.drum = im; $("hopper").style.display = "none"; });
    (CFG.theme.friends || []).forEach(function (path, i) {
      var sp = spots[i % spots.length];
      addChar(path, "friend", sp[0], sp[1], sp[2], function (im) { STAGE.friends.push(im); });
    });
    var bd = new Image();
    bd.onload = function () { $("stage").style.backgroundImage = "url(" + bd.src + ")"; $("stage").classList.remove("has-cover"); STAGE.backdrop = true; };
    bd.src = pub(CFG.theme.backdrop);
    var vid = $("stagevid");
    vid.addEventListener("canplay", function () { vid.hidden = false; vid.play().catch(function () {}); });
    vid.src = pub(CFG.theme.video);
  }

  if (CFG.albumCover) {
    var coverUrl = CFG.supabaseUrl + "/storage/v1/object/public/taal-public/" + CFG.albumCover;
    var probe = new Image();
    probe.onload = function () {
      $("cover").src = coverUrl; $("cover").hidden = false;
      if (!STAGE.backdrop) { $("stage").style.backgroundImage = "url(" + coverUrl + ")"; $("stage").classList.add("has-cover"); }
    };
    probe.src = coverUrl;
  }

  setupSong(CFG.fallbackSong);
  if (sb) {
    sb.from("taal_songs").select("id,title,level,track,tune,plan,sample_audio_path").eq("is_sample", true)
      .order("track").order("created_at").then(function (r) {
        var list = (r.data || []).filter(function (x) { return x.tune && x.plan; });
        if (!list.length) return;
        ALBUM = list;
        var ol = $("tracks"); ol.textContent = "";
        list.forEach(function (x, i) {
          var li = el("li"), b = el("button", { type: "button", "data-id": x.id });
          b.appendChild(el("b", {}, String(x.track || i + 1)));
          var t = el("span", {}, x.title || "Untitled");
          t.appendChild(el("small", {}, "Level " + (x.level || 1) + " · " + x.tune.bpm + " beats a minute"));
          b.appendChild(t);
          b.addEventListener("click", function () {
            albumMode = false; $("playall").textContent = "Play the whole album";
            if (P.playing) stop(false);
            if (P.audio) { P.audio.pause(); }
            setupSong(x);
          });
          li.appendChild(b); ol.appendChild(li);
        });
        if (!P.playing) setupSong(list[0]);
      });
  }

  /* ---------- Family area ---------- */

  var user = null, family = null, pollTimer = 0;
  function say(id, text) { $(id).textContent = text || ""; }
  function problem(err) { return (err && err.message) ? err.message : "Something went wrong. Please try again."; }

  if (!sb) {
    say("signin-msg", "Sign-in is not available right now. Please try again later.");
    return;
  }

  $("signin").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!$("adult").checked) { say("signin-msg", "Please confirm you are a parent or guardian, 18 or over."); return; }
    var email = $("email").value.trim();
    say("signin-msg", "Sending…");
    sb.auth.signInWithOtp({ email: email, options: { emailRedirectTo: location.origin + location.pathname } })
      .then(function (r) {
        say("signin-msg", r.error ? problem(r.error) : "Check " + email + " for your sign-in link. It can take a minute.");
      });
  });
  $("signout").addEventListener("click", function () { sb.auth.signOut(); });

  sb.auth.onAuthStateChange(function (_event, session) {
    var next = session ? session.user : null;
    if ((next && user && next.id === user.id)) return;
    user = next; family = null; clearInterval(pollTimer);
    $("signed-out").hidden = !!user; $("signed-in").hidden = !user;
    if (user) { say("who", "Signed in as " + user.email); setTimeout(loadFamily, 0); }
  });

  function loadFamily() {
    sb.from("taal_families").select("id,name").limit(1).then(function (r) {
      if (r.error) { say("family-msg", problem(r.error)); return; }
      family = r.data[0] || null;
      $("family-form").hidden = !!family;
      $("family-title").hidden = !family;
      $("family-area").hidden = !family;
      if (family) { $("family-title").textContent = family.name; say("family-msg", ""); loadLinks(); loadInstruments(); loadSongs(); }
    });
  }
  $("family-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var name = $("family-name").value.trim();
    if (!name) return;
    sb.from("taal_families").insert({ owner: user.id, name: name }).then(function (r) {
      if (r.error) say("family-msg", problem(r.error)); else loadFamily();
    });
  });

  var WHO = { kid: "The kids", father: "Dad", mother: "Mum", other: "Someone else" };
  function youtubeUrl(u) {
    try { var h = new URL(u).hostname.replace(/^www\.|^m\.|^music\./, ""); return h === "youtube.com" || h === "youtu.be"; }
    catch (e) { return false; }
  }
  function loadLinks() {
    sb.from("taal_links").select("id,url,who,title").order("created_at").then(function (r) {
      var ul = $("links"); ul.textContent = "";
      (r.data || []).forEach(function (l) {
        var li = el("li");
        li.appendChild(el("span", { "class": "tag" }, WHO[l.who] || l.who));
        li.appendChild(el("span", { "class": "grow" }, l.title || l.url));
        var rm = el("button", { "class": "linkbtn", type: "button" }, "Remove");
        rm.addEventListener("click", function () { sb.from("taal_links").delete().eq("id", l.id).then(loadLinks); });
        li.appendChild(rm); ul.appendChild(li);
      });
    });
  }
  $("link-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var url = $("link-url").value.trim();
    if (!youtubeUrl(url)) { say("link-msg", "That doesn't look like a YouTube link. Paste the address of a YouTube video."); return; }
    sb.from("taal_links").insert({ family_id: family.id, url: url, who: $("link-who").value }).then(function (r) {
      if (r.error) { say("link-msg", problem(r.error)); return; }
      $("link-url").value = ""; say("link-msg", "Added."); loadLinks();
    });
  });

  var STATUS = {
    uploaded: ["Reading your photo…", ""],
    ready: ["Ready", "good"],
    needs_tuning: ["Photo read. Note check coming soon", "warn"],
    retake: ["Please send another photo", "warn"]
  };
  var COLOURS = { red: "#e5484d", orange: "#f08c2e", yellow: "#f2c200", green: "#3fa34d", blue: "#2f7fd6", purple: "#8a55d6",
    violet: "#8a55d6", pink: "#e5487a", white: "#f4f4f4", black: "#222", brown: "#8b5a2b", silver: "#b8bcc6", grey: "#8b909c",
    gray: "#8b909c", gold: "#d4a017", teal: "#0e9c8a", cyan: "#22b8cf", wood: "#c49a6c" };
  function loadInstruments() {
    sb.from("taal_instruments").select("id,status,status_reason,profile,created_at").order("created_at").then(function (r) {
      var ul = $("instruments"); ul.textContent = "";
      var waiting = false;
      (r.data || []).forEach(function (i) {
        var st = STATUS[i.status] || [i.status, ""];
        if (i.status === "uploaded") waiting = true;
        var li = el("li");
        li.appendChild(el("span", { "class": "tag " + st[1] }, st[0]));
        var body = el("div", { "class": "grow" });
        body.appendChild(el("strong", {}, i.profile && i.profile.name ? i.profile.name : "Your photo"));
        if (i.profile && i.profile.count) body.appendChild(document.createTextNode(" · " + i.profile.count + " parts"));
        if (i.status_reason && i.status !== "ready") { body.appendChild(el("br")); body.appendChild(document.createTextNode(i.status_reason)); }
        if (i.profile && i.profile.parts && i.profile.parts.length) {
          var parts = el("div", { "class": "parts", "aria-hidden": "true" });
          i.profile.parts.slice(0, 40).forEach(function (p) {
            var c = el("span", { "class": "chip" });
            var col = COLOURS[String(p.colour || "").toLowerCase()];
            if (col) c.style.setProperty("--c", col);
            parts.appendChild(c);
          });
          body.appendChild(parts);
        }
        li.appendChild(body); ul.appendChild(li);
      });
      clearInterval(pollTimer);
      if (waiting) pollTimer = setInterval(loadInstruments, 5000);
    });
  }
  $("inst-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var f = $("inst-file").files[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) { say("inst-msg", "That photo is larger than 5 MB. Please choose a smaller one."); return; }
    var ext = (f.name.split(".").pop() || "jpg").toLowerCase().replace(/[^a-z0-9]/g, "");
    var path = family.id + "/instruments/" + Date.now() + "." + ext;
    say("inst-msg", "Uploading…");
    sb.storage.from("taal").upload(path, f, { contentType: f.type }).then(function (r) {
      if (r.error) { say("inst-msg", problem(r.error)); return; }
      return sb.from("taal_instruments").insert({ family_id: family.id, photo_path: path }).then(function (r2) {
        if (r2.error) { say("inst-msg", problem(r2.error)); return; }
        $("inst-file").value = ""; say("inst-msg", "Uploaded. Taal is reading it now; this takes under a minute."); loadInstruments();
      });
    });
  });

  var SONG_STATUS = { draft: "Being written", checked: "Checked", audio: "Music ready", film: "Film in progress", ready: "Ready", failed: "Needs another try" };
  function loadSongs() {
    sb.from("taal_songs").select("id,title,status,is_sample").eq("family_id", family.id).order("created_at").then(function (r) {
      var ul = $("songs"); ul.textContent = "";
      var rows = r.data || [];
      if (!rows.length) { ul.appendChild(el("li", {}, "No songs yet.")); return; }
      rows.forEach(function (s) {
        var li = el("li");
        li.appendChild(el("span", { "class": "tag" }, SONG_STATUS[s.status] || s.status));
        li.appendChild(el("span", { "class": "grow" }, s.title || "Untitled song"));
        ul.appendChild(li);
      });
    });
  }
})();
