use std::{
    collections::HashMap,
    fs::File,
    io::BufReader,
    path::PathBuf,
    sync::mpsc::{self, Sender},
    thread,
    time::{Duration, Instant},
};

use rodio::{Decoder, OutputStream, Sink};
use tracing::{debug, warn};

#[derive(Debug, Clone)]
pub struct AudioRequest {
    pub path: PathBuf,
    pub volume: f32,
    pub dedupe_key: Option<String>,
    pub play_duplicate: bool,
    pub dedupe_window_ms: u64,
}

#[derive(Clone)]
pub struct AudioPlayer {
    tx: Sender<AudioRequest>,
}

impl AudioPlayer {
    pub fn new() -> Self {
        let (tx, rx) = mpsc::channel::<AudioRequest>();
        thread::spawn(move || {
            let mut output = OutputStream::try_default().ok();
            if output.is_none() {
                warn!("audio output unavailable; event sounds disabled until device is available");
            }
            let mut active_sinks: Vec<Sink> = Vec::new();
            let mut dedupe_until: HashMap<String, Instant> = HashMap::new();

            while let Ok(req) = rx.recv() {
                let now = Instant::now();
                dedupe_until.retain(|_, until| *until > now);
                active_sinks.retain(|sink| !sink.empty());

                if !req.play_duplicate {
                    if let Some(key) = req.dedupe_key.as_ref() {
                        if dedupe_until
                            .get(key)
                            .map(|until| *until > now)
                            .unwrap_or(false)
                        {
                            debug!(key = %key, "skipping duplicate sound");
                            continue;
                        }
                    }
                }

                if output.is_none() {
                    output = OutputStream::try_default().ok();
                    if output.is_none() {
                        continue;
                    }
                }

                let Some((_, handle)) = output.as_ref() else {
                    continue;
                };

                let file = match File::open(&req.path) {
                    Ok(file) => file,
                    Err(err) => {
                        debug!(?err, path = %req.path.display(), "failed opening sound file");
                        continue;
                    }
                };
                let decoder = match Decoder::new(BufReader::new(file)) {
                    Ok(decoder) => decoder,
                    Err(err) => {
                        debug!(?err, path = %req.path.display(), "failed decoding sound file");
                        continue;
                    }
                };

                match Sink::try_new(handle) {
                    Ok(sink) => {
                        sink.set_volume(req.volume.clamp(0.0, 2.0));
                        sink.append(decoder);
                        active_sinks.push(sink);

                        if !req.play_duplicate {
                            if let Some(key) = req.dedupe_key {
                                let window = Duration::from_millis(req.dedupe_window_ms.max(50));
                                dedupe_until.insert(key, now + window);
                            }
                        }
                    }
                    Err(err) => {
                        warn!(?err, "failed to create audio sink");
                        output = None;
                    }
                }
            }
        });
        Self { tx }
    }

    pub fn play(&self, req: AudioRequest) {
        let _ = self.tx.send(req);
    }
}
