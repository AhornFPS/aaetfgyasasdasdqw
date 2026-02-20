use crate::config::OverlayConfig;

#[derive(Debug, Clone)]
pub enum WorkerControlMessage {
    ApplyWorkers(OverlayConfig),
}
