// Public values only. The publishable key is safe in the browser: row-level security does the guarding.
window.TAAL = {
  supabaseUrl: "https://rnwvdwdanyldnrstwxcc.supabase.co",
  supabaseKey: "sb_publishable_tH8Yo0dtrDowqOxfigxX_Q_REZgTtw0",
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
