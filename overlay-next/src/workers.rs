use std::collections::{HashMap, HashSet};

use anyhow::Result;
use chrono::Utc;
use crossbeam_channel::Sender;
use serde_json::json;
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::TcpStream,
    task::JoinHandle,
    time::{sleep, Duration},
};
use tracing::{info, warn};

use crate::{
    events::OverlayEvent,
    protocol::{IncomingMessage, LegacyEnvelope},
};

#[derive(Debug, Clone)]
pub struct TwitchWorkerConfig {
    pub channel: String,
    pub nick: Option<String>,
    pub ignore_special: bool,
    pub ignore_users: Vec<String>,
}

#[derive(Debug)]
struct ParsedPrivmsg {
    author: String,
    raw_user: String,
    text: String,
    color: Option<String>,
}

pub fn spawn_twitch_worker(
    config: TwitchWorkerConfig,
    tx: Sender<IncomingMessage>,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        run_twitch_loop(config, tx).await;
    })
}

async fn run_twitch_loop(config: TwitchWorkerConfig, tx: Sender<IncomingMessage>) {
    let channel = normalize_channel(&config.channel);
    if channel.is_empty() {
        warn!("twitch worker enabled but channel is empty");
        emit_twitch_status(&tx, "ERROR: twitch_channel is empty", false);
        return;
    }

    let ignore_users: HashSet<String> = config
        .ignore_users
        .iter()
        .map(|value| value.trim().to_ascii_lowercase())
        .filter(|value| !value.is_empty())
        .collect();
    info!(channel = %channel, "starting twitch worker");

    loop {
        emit_twitch_status(&tx, format!("JOINING #{channel}..."), false);
        match TcpStream::connect(("irc.chat.twitch.tv", 6667)).await {
            Ok(stream) => {
                let nick = config
                    .nick
                    .clone()
                    .filter(|value| !value.trim().is_empty())
                    .unwrap_or_else(random_justinfan_nick);
                if let Err(err) = run_twitch_session(
                    stream,
                    &channel,
                    &nick,
                    config.ignore_special,
                    &ignore_users,
                    &tx,
                )
                .await
                {
                    warn!(?err, channel = %channel, "twitch worker disconnected");
                }
                emit_twitch_status(&tx, "RECONNECTING (5s)...", false);
            }
            Err(err) => {
                warn!(?err, channel = %channel, "twitch worker failed to connect");
                emit_twitch_status(&tx, "RECONNECTING (5s)...", false);
            }
        }

        sleep(Duration::from_secs(5)).await;
    }
}

async fn run_twitch_session(
    stream: TcpStream,
    channel: &str,
    nick: &str,
    ignore_special: bool,
    ignore_users: &HashSet<String>,
    tx: &Sender<IncomingMessage>,
) -> Result<()> {
    let (read_half, mut write_half) = stream.into_split();
    write_line(
        &mut write_half,
        "CAP REQ :twitch.tv/tags twitch.tv/commands",
    )
    .await?;
    write_line(&mut write_half, "PASS oauth:kappa").await?;
    write_line(&mut write_half, &format!("NICK {nick}")).await?;
    write_line(&mut write_half, &format!("JOIN #{channel}")).await?;

    let mut lines = BufReader::new(read_half).lines();
    info!(channel = %channel, nick = %nick, "twitch worker connected");
    emit_twitch_status(tx, format!("CONNECTED: #{channel}"), true);
    while let Some(line) = lines.next_line().await? {
        let line = line.trim_end_matches('\r');
        if let Some(token) = line.strip_prefix("PING ") {
            write_line(&mut write_half, &format!("PONG {token}")).await?;
            continue;
        }
        if let Some(msg) = parse_privmsg(line, channel) {
            if ignore_special && msg.text.starts_with('!') {
                continue;
            }
            if ignore_users.contains(&msg.raw_user) {
                continue;
            }
            if tx
                .send(IncomingMessage::OverlayEvent(OverlayEvent::TwitchMessage {
                    author: msg.author,
                    text: msg.text,
                    color: msg.color,
                    at: Utc::now(),
                }))
                .is_err()
            {
                warn!("overlay receiver dropped; stopping twitch worker");
                return Ok(());
            }
        }
    }
    Ok(())
}

fn emit_twitch_status(tx: &Sender<IncomingMessage>, status: impl Into<String>, connected: bool) {
    let _ = tx.send(IncomingMessage::Legacy(LegacyEnvelope {
        category: "twitch_status".to_owned(),
        data: json!({
            "status": status.into(),
            "connected": connected,
            "at": Utc::now().to_rfc3339(),
        }),
    }));
}

async fn write_line(writer: &mut tokio::net::tcp::OwnedWriteHalf, line: &str) -> Result<()> {
    writer.write_all(line.as_bytes()).await?;
    writer.write_all(b"\r\n").await?;
    Ok(())
}

fn parse_privmsg(line: &str, expected_channel: &str) -> Option<ParsedPrivmsg> {
    let (tags, payload) = parse_irc_tags(line);
    let mut parts = payload.splitn(4, ' ');
    let prefix = parts.next()?;
    let command = parts.next()?;
    let target = parts.next()?;
    let trailing = parts.next()?;

    if !prefix.starts_with(':') || command != "PRIVMSG" {
        return None;
    }
    if normalize_channel(target) != expected_channel {
        return None;
    }

    let raw_user = prefix[1..]
        .split('!')
        .next()
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();
    if raw_user.is_empty() {
        return None;
    }
    let text = trailing.strip_prefix(':').unwrap_or(trailing).trim();
    if text.is_empty() {
        return None;
    }
    let author = tags
        .get("display-name")
        .filter(|value| !value.is_empty())
        .cloned()
        .unwrap_or_else(|| raw_user.clone());
    let color = tags
        .get("color")
        .and_then(|value| normalize_twitch_color(value));

    Some(ParsedPrivmsg {
        author,
        raw_user,
        text: text.to_owned(),
        color,
    })
}

fn normalize_twitch_color(value: &str) -> Option<String> {
    let trimmed = value.trim();
    if trimmed.len() != 7 || !trimmed.starts_with('#') {
        return None;
    }
    if !trimmed[1..].chars().all(|ch| ch.is_ascii_hexdigit()) {
        return None;
    }
    Some(trimmed.to_ascii_uppercase())
}

fn parse_irc_tags(line: &str) -> (HashMap<String, String>, &str) {
    let Some(stripped) = line.strip_prefix('@') else {
        return (HashMap::new(), line);
    };
    let Some(space_idx) = stripped.find(' ') else {
        return (HashMap::new(), line);
    };

    let tags_part = &stripped[..space_idx];
    let payload = &stripped[(space_idx + 1)..];
    let mut tags = HashMap::new();
    for pair in tags_part.split(';') {
        let Some(eq_idx) = pair.find('=') else {
            continue;
        };
        let key = &pair[..eq_idx];
        let value = decode_irc_tag_value(&pair[(eq_idx + 1)..]);
        tags.insert(key.to_owned(), value);
    }
    (tags, payload)
}

fn decode_irc_tag_value(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    let mut chars = value.chars();
    while let Some(ch) = chars.next() {
        if ch != '\\' {
            out.push(ch);
            continue;
        }
        match chars.next() {
            Some('s') => out.push(' '),
            Some(':') => out.push(';'),
            Some('r') => out.push('\r'),
            Some('n') => out.push('\n'),
            Some('\\') => out.push('\\'),
            Some(other) => {
                out.push('\\');
                out.push(other);
            }
            None => out.push('\\'),
        }
    }
    out
}

fn normalize_channel(value: &str) -> String {
    value.trim().trim_start_matches('#').to_ascii_lowercase()
}

fn random_justinfan_nick() -> String {
    let seed = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|value| value.as_millis() % 90000)
        .unwrap_or(0);
    format!("justinfan{}", 10000 + seed)
}

#[cfg(test)]
mod tests {
    use super::{decode_irc_tag_value, normalize_channel, parse_privmsg};

    #[test]
    fn parses_privmsg_with_display_name() {
        let line = "@display-name=Ahorn;color=#1E90FF;user-id=1 :ahorn!ahorn@ahorn.tmi.twitch.tv PRIVMSG #HornGaming :hello world";
        let parsed = parse_privmsg(line, "horngaming").expect("expected parse");
        assert_eq!(parsed.author, "Ahorn");
        assert_eq!(parsed.raw_user, "ahorn");
        assert_eq!(parsed.text, "hello world");
        assert_eq!(parsed.color.as_deref(), Some("#1E90FF"));
    }

    #[test]
    fn parse_privmsg_rejects_wrong_channel() {
        let line = ":foo!foo@foo.tmi.twitch.tv PRIVMSG #other :hello";
        assert!(parse_privmsg(line, "expected").is_none());
    }

    #[test]
    fn decodes_irc_tag_escapes() {
        assert_eq!(
            decode_irc_tag_value("A\\sB\\:C\\\\D"),
            "A B;C\\D".to_owned()
        );
    }

    #[test]
    fn parse_privmsg_ignores_invalid_color_values() {
        let line =
            "@display-name=Ahorn;color=nothex :ahorn!ahorn@ahorn.tmi.twitch.tv PRIVMSG #HornGaming :hello";
        let parsed = parse_privmsg(line, "horngaming").expect("expected parse");
        assert!(parsed.color.is_none());
    }

    #[test]
    fn normalizes_channel_names() {
        assert_eq!(normalize_channel("#TestChan "), "testchan".to_owned());
    }
}
