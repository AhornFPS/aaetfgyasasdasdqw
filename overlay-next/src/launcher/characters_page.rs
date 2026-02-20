use std::sync::mpsc;
use std::thread;

use eframe::egui::{self, Color32, Key, RichText, Ui};

use crate::app::OverlayState;
use crate::dior_db::CharacterDatabase;
use crate::launcher::CharactersSubTab;

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    poll_search_result(app);

    ui.spacing_mut().item_spacing.y = 10.0;
    let mut trigger_search = false;

    ui.horizontal(|ui| {
        ui.label(
            RichText::new("CHARACTER ANALYSIS")
                .size(20.0)
                .strong()
                .color(Color32::from_rgb(0, 242, 255)),
        );
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if draw_action_button(ui, "SEARCH", [100.0, 34.0]).clicked() {
                trigger_search = true;
            }
            let response = ui.add_sized(
                [250.0, 34.0],
                egui::TextEdit::singleline(&mut app.launcher.characters.query)
                    .hint_text("Enter Character Name..."),
            );
            if response.lost_focus() && ui.input(|input| input.key_pressed(Key::Enter)) {
                trigger_search = true;
            }
        });
    });

    ui.add_space(6.0);
    ui.horizontal(|ui| {
        if crate::launcher::theme::top_nav_button(
            ui,
            "OVERVIEW",
            app.launcher.characters.selected_tab == CharactersSubTab::Overview,
        )
        .clicked()
        {
            app.launcher.characters.selected_tab = CharactersSubTab::Overview;
        }
        if crate::launcher::theme::top_nav_button(
            ui,
            "WEAPON STATS",
            app.launcher.characters.selected_tab == CharactersSubTab::WeaponStats,
        )
        .clicked()
        {
            app.launcher.characters.selected_tab = CharactersSubTab::WeaponStats;
        }
        if crate::launcher::theme::top_nav_button(
            ui,
            "DIRECTIVES",
            app.launcher.characters.selected_tab == CharactersSubTab::Directives,
        )
        .clicked()
        {
            app.launcher.characters.selected_tab = CharactersSubTab::Directives;
        }
    });

    ui.add_space(6.0);
    egui::Frame::none()
        .fill(Color32::from_rgba_premultiplied(20, 20, 20, 204))
        .stroke(egui::Stroke::new(1.0, Color32::from_rgb(51, 51, 51)))
        .inner_margin(egui::Margin::same(14.0))
        .show(ui, |ui| match app.launcher.characters.selected_tab {
            CharactersSubTab::Overview => draw_overview(app, ui),
            CharactersSubTab::WeaponStats => draw_weapon_stats(app, ui),
            CharactersSubTab::Directives => draw_directives(app, ui),
        });

    ui.add_space(10.0);
    draw_log_area(app, ui);

    if trigger_search {
        start_character_search(app);
    }
}

fn draw_action_button(ui: &mut Ui, label: &str, size: [f32; 2]) -> egui::Response {
    ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = Color32::from_rgb(51, 51, 51);
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, Color32::from_rgb(68, 68, 68));
        visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.0, Color32::from_rgb(238, 238, 238));
        visuals.widgets.hovered.bg_fill = Color32::from_rgb(68, 68, 68);
        visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, Color32::from_rgb(0, 242, 255));
        visuals.widgets.hovered.fg_stroke = egui::Stroke::new(1.0, Color32::WHITE);
        ui.add_sized(size, egui::Button::new(label))
    })
    .inner
}

fn start_character_search(app: &mut OverlayState) {
    let query = app.launcher.characters.query.trim().to_owned();
    if query.is_empty() {
        app.launcher.characters.status = Some("Enter a character name.".to_owned());
        return;
    }

    let sid = app
        .config
        .census_service_id
        .as_ref()
        .map(String::as_str)
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("example")
        .to_owned();
    let db_path = app.character_db_path.clone();
    let (tx, rx) = mpsc::channel();
    app.launcher.characters.search_result = Some(rx);
    app.launcher.characters.status = Some(format!("UPLINK: Requesting data for Character '{query}'..."));

    thread::spawn(move || {
        let result = crate::census::lookup_character_by_name(&sid, &query, Some(db_path));
        let _ = tx.send(result);
    });
}

fn poll_search_result(app: &mut OverlayState) {
    let mut finished = false;
    let mut success = None;
    let mut error = None;

    if let Some(rx) = &app.launcher.characters.search_result {
        match rx.try_recv() {
            Ok(result) => {
                finished = true;
                match result {
                    Ok(entry) => success = Some(entry),
                    Err(err) => error = Some(err),
                }
            }
            Err(mpsc::TryRecvError::Disconnected) => {
                finished = true;
                error = Some("Character search worker disconnected.".to_owned());
            }
            Err(mpsc::TryRecvError::Empty) => {}
        }
    }

    if !finished {
        return;
    }

    app.launcher.characters.search_result = None;
    if let Some(entry) = success {
        app.launcher.characters.query.clear();
        app.launcher.characters.selected_character = Some(entry.clone());
        app.launcher.characters.selected_profile =
            CharacterDatabase::open(app.character_db_path.clone())
                .ok()
                .and_then(|db| db.find_player_cache_entry(&entry.character_id).ok().flatten());
        app.launcher.characters.status = Some(format!("Loaded '{}' ({})", entry.name, entry.character_id));
    }
    if let Some(err) = error {
        app.launcher.characters.status = Some(format!("Search failed: {err}"));
    }
}

fn draw_overview(app: &mut OverlayState, ui: &mut Ui) {
    let Some(character) = app.launcher.characters.selected_character.as_ref() else {
        ui.label("Search a character to view overview data.");
        return;
    };
    let profile = app.launcher.characters.selected_profile.as_ref();
    let world_id = profile
        .and_then(|entry| entry.world_id.as_deref())
        .or(character.world_id.as_deref())
        .unwrap_or("0");
    let faction = profile
        .and_then(|entry| entry.faction_id)
        .map(faction_name_from_id)
        .unwrap_or("Unknown");
    let outfit = profile
        .and_then(|entry| entry.outfit_tag.as_deref())
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("-");
    let rank = profile
        .and_then(|entry| entry.battle_rank)
        .map(|value| value.to_string())
        .unwrap_or_else(|| "-".to_owned());
    let server = server_name_from_world_id(world_id);

    let spacing = 14.0;
    let total_w = ui.available_width().max(0.0);
    let left_w = (total_w * 0.34).max(250.0);
    let right_w = (total_w - left_w - spacing).max(300.0);
    ui.horizontal_top(|ui| {
        ui.spacing_mut().item_spacing.x = spacing;
        draw_stat_card(ui, left_w, "GENERAL INFORMATION", |ui| {
            stat_row(ui, "Name:", &character.name);
            stat_row(ui, "Faction:", faction);
            stat_row(ui, "Server:", server);
            stat_row(ui, "Outfit:", outfit);
            stat_row(ui, "Rank:", &rank);
            stat_row(ui, "Time Played:", "-");
        });
        draw_stat_card(ui, right_w, "PERFORMANCE", |ui| {
            ui.columns(2, |cols| {
                draw_perf_column(&mut cols[0], "LIFETIME PERFORMANCE");
                draw_perf_column(&mut cols[1], "LAST 30 DAYS");
            });
        });
    });
}

fn draw_stat_card(ui: &mut Ui, width: f32, title: &str, add_contents: impl FnOnce(&mut Ui)) {
    ui.allocate_ui_with_layout(
        egui::vec2(width, 0.0),
        egui::Layout::top_down(egui::Align::Min),
        |ui| {
            egui::Frame::none()
                .fill(Color32::from_rgba_premultiplied(30, 30, 30, 153))
                .stroke(egui::Stroke::new(1.0, Color32::from_rgb(51, 51, 51)))
                .inner_margin(egui::Margin::same(10.0))
                .show(ui, |ui| {
                    ui.label(
                        RichText::new(title)
                            .size(15.0)
                            .strong()
                            .color(Color32::from_rgb(0, 242, 255)),
                    );
                    ui.add_space(8.0);
                    add_contents(ui);
                });
        },
    );
}

fn stat_row(ui: &mut Ui, label: &str, value: &str) {
    ui.horizontal(|ui| {
        ui.label(
            RichText::new(label)
                .size(12.0)
                .color(Color32::from_rgb(136, 136, 136)),
        );
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            ui.label(RichText::new(value).size(16.0).strong().color(Color32::WHITE));
        });
    });
}

fn draw_perf_column(ui: &mut Ui, title: &str) {
    ui.label(
        RichText::new(title)
            .size(15.0)
            .strong()
            .color(Color32::from_rgb(0, 242, 255)),
    );
    for stat in ["Kills", "Deaths", "K/D", "KPM", "KPH", "SPM", "Score"] {
        ui.label(
            RichText::new(stat)
                .size(12.0)
                .color(Color32::from_rgb(136, 136, 136)),
        );
        ui.label(RichText::new("-").size(16.0).strong().color(Color32::WHITE));
    }
}

fn draw_weapon_stats(app: &mut OverlayState, ui: &mut Ui) {
    let Some(character) = app.launcher.characters.selected_character.as_ref() else {
        ui.label("Search a character first.");
        return;
    };
    ui.label(
        RichText::new(format!(
            "Weapon stats target: {} ({})",
            character.name, character.character_id
        ))
        .small()
        .color(Color32::from_rgb(140, 140, 140)),
    );
    ui.add_space(6.0);
    draw_table_shell(
        ui,
        &[
            ("WEAPON", 200.0),
            ("KILLS", 68.0),
            ("KPM", 58.0),
            ("K/D", 58.0),
            ("ACC %", 58.0),
            ("HSR %", 58.0),
            ("V.KILLS", 62.0),
            ("V.KPM", 62.0),
            ("TIME", 80.0),
        ],
        &[],
        360.0,
    );
}

fn draw_directives(app: &mut OverlayState, ui: &mut Ui) {
    let Some(character) = app.launcher.characters.selected_character.as_ref() else {
        ui.label("Search a character first.");
        return;
    };
    ui.label(
        RichText::new(format!(
            "Directive lookup target: {} ({})",
            character.name, character.character_id
        ))
        .small()
        .color(Color32::from_rgb(140, 140, 140)),
    );
    ui.add_space(6.0);
    draw_table_shell(
        ui,
        &[
            ("DIRECTIVE LINE", 360.0),
            ("CURRENT TIER", 140.0),
            ("STATUS", 140.0),
        ],
        &[],
        360.0,
    );
}

fn draw_table_shell(
    ui: &mut Ui,
    columns: &[(&str, f32)],
    rows: &[Vec<String>],
    height: f32,
) {
    egui::Frame::none()
        .fill(Color32::from_rgb(26, 26, 26))
        .inner_margin(egui::Margin::symmetric(0.0, 0.0))
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                for (label, width) in columns {
                    ui.add_sized(
                        [*width, 28.0],
                        egui::Label::new(
                            RichText::new(*label)
                                .small()
                                .strong()
                                .color(Color32::from_rgb(0, 242, 255)),
                        ),
                    );
                }
            });
            egui::Frame::none()
                .fill(Color32::from_rgb(16, 16, 16))
                .show(ui, |ui| {
                    ui.set_min_height(height);
                    egui::ScrollArea::vertical()
                        .auto_shrink([false, false])
                        .show(ui, |ui| {
                            if rows.is_empty() {
                                ui.label(
                                    RichText::new("No rows loaded yet.")
                                        .small()
                                        .color(Color32::from_rgb(120, 120, 120)),
                                );
                            } else {
                                for row in rows {
                                    ui.horizontal(|ui| {
                                        for ((_, width), cell) in columns.iter().zip(row.iter()) {
                                            ui.add_sized(
                                                [*width, 22.0],
                                                egui::Label::new(
                                                    RichText::new(cell)
                                                        .small()
                                                        .color(Color32::WHITE),
                                                ),
                                            );
                                        }
                                    });
                                }
                            }
                        });
                });
        });
}

fn draw_log_area(app: &OverlayState, ui: &mut Ui) {
    let log_text = app
        .launcher
        .characters
        .status
        .clone()
        .unwrap_or_else(|| "LOG: waiting for character actions...".to_owned());
    let mut buffer = log_text;
    egui::Frame::none()
        .fill(Color32::from_rgb(5, 5, 5))
        .stroke(egui::Stroke::new(1.0, Color32::from_rgb(51, 51, 51)))
        .inner_margin(egui::Margin::same(8.0))
        .show(ui, |ui| {
            ui.add_sized(
                [ui.available_width(), 150.0],
                egui::TextEdit::multiline(&mut buffer)
                    .desired_rows(8)
                    .font(egui::TextStyle::Monospace)
                    .interactive(false),
            );
        });
}

fn faction_name_from_id(faction_id: i64) -> &'static str {
    match faction_id {
        1 => "VS",
        2 => "NC",
        3 => "TR",
        4 => "NSO",
        _ => "Unknown",
    }
}

fn server_name_from_world_id(world_id: &str) -> &'static str {
    match world_id {
        "10" | "13" => "Wainwright (EU)",
        "1" | "17" => "Osprey (US)",
        "40" => "SolTech (Asia)",
        "19" => "Jaeger (Events)",
        _ => "Unknown",
    }
}
