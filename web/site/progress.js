/* Taal progress and rewards: who is playing, stars per song, "next for you", level-up,
   and a weekly line per child for parents. Saved only when a parent is signed in and
   has added the child; otherwise the stars still show but are not kept. */
(function () {
  "use strict";
  var CFG = window.TAAL;
  var $ = function (id) { return document.getElementById(id); };
  if (!window.supabase || !$("reward")) return;
  var sb = window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseKey);
  var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  var user = null, family = null, kids = [], childId = null, plays = [], album = [];

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    for (var k in (attrs || {})) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  function stars(n) {
    var s = el("span", { "class": "trackstars", "aria-label": n + " of 3 stars" });
    for (var i = 1; i <= 3; i++) {
      var x = el("span", i <= n ? {} : { "class": "off" }, "★");
      s.appendChild(x);
    }
    return s;
  }
  function starsFor(ratio, turn) {
    if (!turn) return 1;
    return ratio >= 0.75 ? 3 : ratio >= 0.4 ? 2 : 1;
  }
  function kid() { return kids.filter(function (k) { return k.id === childId; })[0] || null; }
  function myPlays() { return plays.filter(function (p) { return p.child_id === childId; }); }
  function best() {
    var b = {};
    myPlays().forEach(function (p) { if (p.song_id) b[p.song_id] = Math.max(b[p.song_id] || 0, p.stars); });
    return b;
  }
  // Each level opens after three songs of the level below have two stars or more.
  // Levels nobody has songs for yet are skipped over, so a gap never blocks a child.
  var LEVEL_NAMES = { 2: "five notes", 3: "rhythm songs", 4: "six notes", 5: "the whole ladder, C to high C" };
  function unlocked(b) {
    var top = album.reduce(function (m, s) { return Math.max(m, s.level || 1); }, 1);
    var lvl = 1;
    while (lvl < top) {
      var here = album.filter(function (s) { return (s.level || 1) === lvl; });
      if (here.length) {
        var good = here.filter(function (s) { return (b[s.id] || 0) >= 2; }).length;
        if (good < Math.min(3, here.length)) break;
      }
      lvl++;
    }
    return lvl;
  }

  /* ---------- drawing ---------- */
  function drawWho() {
    var bar = $("whobar"), chips = $("who-chips");
    chips.textContent = "";
    if (!user || !family || !kids.length) { bar.hidden = true; return; }
    bar.hidden = false;
    kids.forEach(function (k) {
      var b = el("button", { type: "button", "aria-pressed": k.id === childId ? "true" : "false" }, k.name);
      b.addEventListener("click", function () { pick(k.id); });
      chips.appendChild(b);
    });
  }
  function pick(id) {
    childId = id;
    try { localStorage.setItem("taal-child-" + family.id, id); } catch (e) {}
    drawAll();
  }
  function drawTracks() {
    var b = best(), lvl = unlocked(b), on = !!(user && kid());
    Array.prototype.forEach.call(document.querySelectorAll("#tracks button[data-id]"), function (btn) {
      var old = btn.querySelector(".trackstars"); if (old) old.remove();
      var s = album.filter(function (x) { return x.id === btn.dataset.id; })[0];
      btn.classList.toggle("later", on && !!s && (s.level || 1) > lvl);
      if (on && b[btn.dataset.id]) btn.querySelector("span").appendChild(stars(b[btn.dataset.id]));
    });
  }
  function nextSong() {
    var b = best(), lvl = unlocked(b);
    var open = album.filter(function (s) { return (s.level || 1) <= lvl; });
    return open.filter(function (s) { return (b[s.id] || 0) < 2; })[0] ||
           open.filter(function (s) { return (b[s.id] || 0) < 3; })[0] || null;
  }
  function drawNext() {
    var box = $("nextup"); box.textContent = "";
    var k = kid();
    if (!user || !k || !album.length) { box.hidden = true; return; }
    var s = nextSong();
    box.hidden = false;
    var left = el("span");
    if (s) {
      left.appendChild(document.createTextNode("Next for " + k.name + ": "));
      left.appendChild(el("b", {}, s.title));
      var go = el("button", { "class": "btn primary", type: "button" }, "Play it");
      go.addEventListener("click", function () {
        if (window.TaalPlayer) window.TaalPlayer.select(s.id);
        var p = document.querySelector(".player"); if (p) p.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      box.appendChild(left); box.appendChild(go);
    } else {
      left.appendChild(el("b", {}, k.name + " has three stars on every song!"));
      left.appendChild(document.createTextNode(" Make a new one in Studio."));
      box.appendChild(left);
    }
  }
  function week(k) {
    var since = Date.now() - 7 * 864e5;
    var w = plays.filter(function (p) { return p.child_id === k.id && new Date(p.created_at).getTime() >= since; });
    var mins = Math.round(w.reduce(function (a, p) { return a + p.seconds; }, 0) / 60);
    var songs = {}; w.forEach(function (p) { if (p.song_id) songs[p.song_id] = 1; });
    var starsN = w.reduce(function (a, p) { return a + p.stars; }, 0);
    // Notes learned: the notes of every song played with two stars or more, ever.
    var notes = {};
    plays.forEach(function (p) {
      if (p.child_id !== k.id || p.stars < 2) return;
      var s = album.filter(function (x) { return x.id === p.song_id; })[0];
      if (s && s.tune) s.tune.notes.forEach(function (n) { notes[n.pitch[0]] = 1; });
    });
    var order = "CDEFGAB".split("").filter(function (n) { return notes[n]; });
    if (!w.length) return "Not played this week yet." + (order.length ? " Knows " + order.join(" ") + "." : "");
    return "This week: " + (mins || "under 1") + " min, " + Object.keys(songs).length + " song" +
      (Object.keys(songs).length === 1 ? "" : "s") + ", " + starsN + " stars." +
      (order.length ? " Knows " + order.join(" ") + "." : "");
  }
  function drawKids() {
    var ul = $("kids"); if (!ul) return;
    ul.textContent = "";
    kids.forEach(function (k) {
      var li = el("li");
      li.appendChild(el("b", {}, k.name));
      li.appendChild(el("span", { "class": "week" }, week(k)));
      ul.appendChild(li);
    });
  }
  function drawAll() { drawWho(); drawTracks(); drawNext(); drawKids(); }

  /* ---------- the moment a song ends ---------- */
  window.addEventListener("taal:finished", function (e) {
    var d = e.detail || {}, s = d.song || {};
    var n = starsFor(d.turn ? d.hits / d.turn : 0, d.turn);
    var box = $("reward"); box.textContent = ""; box.hidden = false;
    var big = el("div", { "class": "stars", "aria-label": n + " of 3 stars" });
    for (var i = 1; i <= 3; i++) big.appendChild(el("span", i <= n ? {} : { "class": "off" }, "★"));
    box.appendChild(big);
    var k = kid();
    var who = k ? k.name : "You";
    box.appendChild(el("p", {}, n === 3 ? who + " played it beautifully!" : n === 2 ? "Well done, " + who + "! One more go for three stars?" :
      "You finished the song! Next time, play when the key lights up."));
    var can = user && family && k && s.id && UUID.test(String(s.id)) && !s.draft;
    if (!can) {
      if (!user) box.appendChild(el("p", { "class": "muted" }, "Sign in under Your family to keep stars."));
      else if (!kids.length) box.appendChild(el("p", { "class": "muted" }, "Add your child under Your family to keep stars."));
      return;
    }
    var before = unlocked(best());
    var row = { family_id: family.id, child_id: k.id, song_id: s.id, song_level: s.level || 1,
      instrument: d.instrument || "keys", turn_notes: d.turn || 0, hits: Math.min(d.hits || 0, d.turn || 0),
      stars: n, seconds: Math.max(0, Math.min(3600, d.seconds || 0)) };
    sb.from("taal_plays").insert(row).select("child_id,song_id,stars,seconds,created_at").then(function (r) {
      if (r.error) { box.appendChild(el("p", { "class": "muted" }, "Couldn't save the stars this time.")); return; }
      plays.unshift(r.data[0]);
      var after = unlocked(best());
      if (after > before) {
        box.appendChild(el("div", { "class": "levelup" }, k.name + " reached level " + after + "! Songs with " + (LEVEL_NAMES[after] || "new notes") + " are open now."));
      }
      drawAll();
    });
  });

  // A new play starts fresh.
  if ($("playbtn")) $("playbtn").addEventListener("click", function () { $("reward").hidden = true; });
  if ($("tracks")) $("tracks").addEventListener("click", function () { $("reward").hidden = true; });

  window.addEventListener("taal:album", function (e) { album = e.detail || []; drawAll(); });
  window.addEventListener("taal:tracks", function () { drawTracks(); });

  /* ---------- signing in, children ---------- */
  function load() {
    sb.from("taal_families").select("id,name").limit(1).then(function (r) {
      family = (r.data || [])[0] || null;
      if (!family) { kids = []; drawAll(); return; }
      sb.from("taal_children").select("id,name").eq("family_id", family.id).order("created_at").then(function (rk) {
        kids = rk.data || [];
        var saved = null; try { saved = localStorage.getItem("taal-child-" + family.id); } catch (e) {}
        childId = kids.some(function (k) { return k.id === saved; }) ? saved : (kids[0] ? kids[0].id : null);
        sb.from("taal_plays").select("child_id,song_id,stars,seconds,created_at").eq("family_id", family.id)
          .order("created_at", { ascending: false }).limit(2000).then(function (rp) {
            plays = rp.data || [];
            drawAll();
          });
      });
    });
  }
  sb.auth.onAuthStateChange(function (_ev, session) {
    var next = session ? session.user : null;
    if (next && user && next.id === user.id) return;
    user = next; family = null; kids = []; plays = []; childId = null;
    if (user) setTimeout(load, 0); else drawAll();
  });

  var form = $("kid-form");
  if (form) form.addEventListener("submit", function (e) {
    e.preventDefault();
    var name = $("kid-name").value.trim().slice(0, 30);
    if (!family) { $("kid-msg").textContent = "One moment… press Add again."; load(); return; }
    if (!$("kid-consent").checked) { $("kid-msg").textContent = "Please tick the box first."; return; }
    sb.from("taal_children").insert({ family_id: family.id, name: name, consent: true }).select("id,name").then(function (r) {
      if (r.error) { $("kid-msg").textContent = r.error.message; return; }
      kids.push(r.data[0]); $("kid-name").value = ""; $("kid-consent").checked = false;
      $("kid-msg").textContent = name + " is added. Pick them under “Who's playing?”.";
      if (!childId) childId = r.data[0].id;
      drawAll();
    });
  });
})();
