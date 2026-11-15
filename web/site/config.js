// Public values only. The publishable key is safe in the browser: row-level security does the guarding.
window.TAAL = {
  supabaseUrl: "https://rnwvdwdanyldnrstwxcc.supabase.co",
  supabaseKey: "sb_publishable_tH8Yo0dtrDowqOxfigxX_Q_REZgTtw0",
  albumCover: "covers/album1-v1",
  albums: [
    { id: "album1", eyebrow: "Album one", title: "Three Little Notes and friends", tab: "Album one · 3 notes",
      blurb: "Nine songs. The first six use three notes; the last three add two more.", cover: "covers/album1-v1",
      alt: "Album cover: a smiling drum and its friends playing music by a paper pond" },
    { id: "album2", eyebrow: "Album two", title: "Five Notes, All Day Long", tab: "Album two · 5 notes",
      blurb: "Nine songs from morning to bedtime, all on five notes: C, D, E, G and A.", cover: "covers/album2-v1",
      alt: "Album cover: a little drum and friends greeting the morning sun" },
    { id: "album3", eyebrow: "Album three", title: "Animal Parade", tab: "Album three · rhythm",
      blurb: "Nine animal songs on the same five notes, with long notes, short notes and rests.", cover: "covers/album3-v1",
      alt: "Album cover: a little drum leading a parade of paper animals" }
  ],
  // The stage: an animated backdrop, and characters the page moves on the beat.
  theme: {
    name: "Paper pond",
    video: "themes/pond/loop-v1",
    backdrop: "themes/pond/backdrop-v1",
    drum: "themes/pond/drum-v1",
    friends: ["themes/pond/duck-v1", "themes/pond/turtle-v1", "themes/pond/firefly-v1"]
  },
  // Bands the child can choose. Each is a key picture plus five short film clips that start and
  // end on that picture and stand for two bars of music. When casts exist they replace the
  // cut-out theme above.
  // false = no picture on the player (15 Nov: band pictures looked off). Casts kept for later.
  stage: false,
  // The family lyre: notes from the longest string (1) to the shortest (7). Usual children's lyre tuning.
  lyre: { strings: ["D4", "E4", "G4", "A4", "B4", "D5", "E5"] },
  casts: [
    { id: "forest", name: "Forest band", poster: "themes/forest3d/key-v1", clipSeconds: 5,
      clips: { play: "themes/forest3d/play-v1", turn: "themes/forest3d/turn-v1", together: "themes/forest3d/together-v1", intro: "themes/forest3d/intro-v1", outro: "themes/forest3d/outro-v1" } },
    { id: "mermaid", name: "Mermaid lagoon", poster: "themes/mermaid3d/key-v1", clipSeconds: 5,
      clips: { play: "themes/mermaid3d/play-v1", turn: "themes/mermaid3d/turn-v1", together: "themes/mermaid3d/together-v1", intro: "themes/mermaid3d/intro-v1", outro: "themes/mermaid3d/outro-v1" } },
    { id: "hero", name: "Hero rooftop", poster: "themes/hero3d/key-v1", clipSeconds: 5,
      clips: { play: "themes/hero3d/play-v1", turn: "themes/hero3d/turn-v1", together: "themes/hero3d/together-v1", intro: "themes/hero3d/intro-v1", outro: "themes/hero3d/outro-v1" } },
    { id: "folk", name: "Village courtyard", poster: "themes/folk2d/key-v1", clipSeconds: 5,
      clips: { play: "themes/folk2d/play-v1", turn: "themes/folk2d/turn-v1", together: "themes/folk2d/together-v1", intro: "themes/folk2d/intro-v1", outro: "themes/folk2d/outro-v1" } }
  ],
  // Shown if the database cannot be reached.
  fallbackSong: {
    id: "d3b59e85-17c7-45b9-8c27-bb9284d39454",
    title: "Three Little Notes",
    level: 1,
    sample_audio_path: "samples/d3b59e85-17c7-45b9-8c27-bb9284d39454/backing.mp3",
    tune: { bpm: 96, beats_per_bar: 4, notes: [
      { pitch: "C4", start: 0, length: 1 }, { pitch: "D4", start: 1, length: 1 }, { pitch: "E4", start: 2, length: 1 },
      { pitch: "E4", start: 4, length: 1 }, { pitch: "D4", start: 5, length: 1 }, { pitch: "C4", start: 6, length: 1 },
      { pitch: "C4", start: 8, length: 1 }, { pitch: "D4", start: 9, length: 1 }, { pitch: "E4", start: 10, length: 1 },
      { pitch: "E4", start: 12, length: 1 }, { pitch: "D4", start: 13, length: 1 }, { pitch: "C4", start: 14, length: 1 }
    ] },
    plan: { bpm: 96, beats_per_bar: 4, sections: [
      { name: "Intro", bars: 2, kind: "listen" }, { name: "Listen", bars: 4, kind: "listen" },
      { name: "Your turn", bars: 4, kind: "turn" }, { name: "Together", bars: 4, kind: "listen" },
      { name: "Outro", bars: 2, kind: "listen" }
    ] }
  }
};
