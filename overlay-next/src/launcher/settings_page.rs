use eframe::egui::{self, Slider, Ui};
use std::path::{Path, PathBuf};

use crate::app::OverlayState;

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    let mut config_changed = false;
    ui.spacing_mut().item_spacing.y = 20.0;

    ui.label(
        egui::RichText::new("GLOBAL CONFIGURATION")
            .size(24.0)
            .strong()
            .color(egui::Color32::from_rgb(0, 242, 255)),
    );

    draw_group(
        ui,
        "PLANETSIDE 2 DIRECTORY",
        Some("Required for UserOptions.ini modifications (Launcher)"),
        |ui| {
            ui.horizontal(|ui| {
                let label_w = (ui.available_width() - 160.0).max(220.0);
                path_label_sized(
                    ui,
                    app.config
                        .ps2_path
                        .as_deref()
                        .filter(|value| !value.trim().is_empty())
                        .unwrap_or("NOT_FOUND (Please Browse)"),
                    label_w,
                );
                let browse_clicked = draw_action_button(
                    ui,
                    "BROWSE FOLDER",
                    [150.0, 36.0],
                    egui::Color32::from_rgb(51, 51, 51),
                    egui::Color32::from_rgb(68, 68, 68),
                    egui::Color32::from_rgb(0, 242, 255),
                );
                if browse_clicked {
                    if let Some(found) = detect_ps2_path() {
                        app.config.ps2_path = Some(found.display().to_string());
                        app.launcher.settings_status =
                            Some(format!("Detected PS2 folder: {}", found.display()));
                        config_changed = true;
                    } else {
                        app.launcher.settings_status =
                            Some("Auto-detect failed. Paste PS2 path manually.".to_owned());
                    }
                }
            });
        },
    );

    draw_group(ui, "AUDIO SETTINGS", None, |ui| {
        ui.horizontal(|ui| {
            ui.label(egui::RichText::new("Master Volume:").color(egui::Color32::WHITE));
            let mut volume = (app.config.sound_master_volume * 100.0).round() as i32;
            let slider_w = (ui.available_width() - 58.0).max(120.0);
            if ui
                .add_sized(
                    [slider_w, 24.0],
                    Slider::new(&mut volume, 0..=100).show_value(false),
                )
                .changed()
            {
                app.config.sound_master_volume = (volume as f32 / 100.0).clamp(0.0, 1.0);
                config_changed = true;
            }
            ui.add_sized(
                [40.0, 18.0],
                egui::Label::new(
                    egui::RichText::new(format!("{volume}%"))
                        .strong()
                        .monospace()
                        .color(egui::Color32::from_rgb(0, 242, 255)),
                ),
            );
        });
        ui.horizontal(|ui| {
            ui.label(egui::RichText::new("Output Device:").color(egui::Color32::WHITE));
            let mut device = "Default".to_owned();
            egui::ComboBox::from_id_source("settings_audio_device")
                .selected_text(&device)
                .width(ui.available_width())
                .show_ui(ui, |ui| {
                    ui.selectable_value(&mut device, "Default".to_owned(), "Default");
                });
        });
    });

    draw_group(ui, "CLIENT APPEARANCE", None, |ui| {
        ui.label(
            egui::RichText::new("Menu Background Image:")
                .color(egui::Color32::from_rgb(170, 170, 170)),
        );
        ui.horizontal(|ui| {
            let label_w = (ui.available_width() - 270.0).max(220.0);
            let current_bg = app
                .config
                .main_background_path
                .as_deref()
                .filter(|value| !value.is_empty())
                .map(filename_from_path)
                .unwrap_or("No image selected");
            path_label_sized(ui, current_bg, label_w);

            let change_clicked = draw_action_button(
                ui,
                "CHANGE IMAGE",
                [160.0, 36.0],
                egui::Color32::from_rgb(51, 51, 51),
                egui::Color32::from_rgb(68, 68, 68),
                egui::Color32::from_rgb(0, 242, 255),
            );
            if change_clicked {
                if app.config.main_background_path.is_none() {
                    app.config.main_background_path =
                        Some("assets/Images/background.jpg".to_owned());
                }
                config_changed = true;
            }

            let clear_clicked = draw_action_button(
                ui,
                "CLEAR",
                [96.0, 36.0],
                egui::Color32::from_rgb(68, 0, 0),
                egui::Color32::from_rgb(85, 0, 0),
                egui::Color32::from_rgb(255, 68, 68),
            );
            if clear_clicked {
                app.config.main_background_path = None;
                config_changed = true;
            }
        });
    });

    draw_group(
        ui,
        "DISCORD INTEGRATION",
        Some("Share your current character, server, and last seen base in Discord Rich Presence."),
        |ui| {
            ui.horizontal(|ui| {
                ui.label(
                    egui::RichText::new("Discord Rich Presence:")
                        .color(egui::Color32::from_rgb(170, 170, 170)),
                );
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let enabled = app.config.discord_presence_active;
                    let (bg, hover, text) = if enabled {
                        (
                            egui::Color32::from_rgb(0, 68, 0),
                            egui::Color32::from_rgb(0, 85, 0),
                            egui::Color32::WHITE,
                        )
                    } else {
                        (
                            egui::Color32::from_rgb(68, 0, 0),
                            egui::Color32::from_rgb(85, 0, 0),
                            egui::Color32::from_rgb(255, 204, 204),
                        )
                    };
                    let label = if enabled { "ENABLED" } else { "DISABLED" };
                    let toggle_clicked =
                        draw_action_button(ui, label, [150.0, 36.0], bg, hover, text);
                    if toggle_clicked {
                        app.config.discord_presence_active = !app.config.discord_presence_active;
                        config_changed = true;
                    }
                });
            });
        },
    );

    ui.add_space(6.0);
    let save_clicked = draw_action_button(
        ui,
        "SAVE SETTINGS",
        [220.0, 44.0],
        egui::Color32::from_rgb(0, 102, 0),
        egui::Color32::from_rgb(0, 170, 0),
        egui::Color32::from_rgb(0, 255, 0),
    );
    if save_clicked {
        let _ = app.save_settings_now();
    }

    let updates_clicked = draw_action_button(
        ui,
        "CHECK FOR UPDATES",
        [220.0, 36.0],
        egui::Color32::from_rgb(51, 51, 51),
        egui::Color32::from_rgb(68, 68, 68),
        egui::Color32::from_rgb(0, 242, 255),
    );
    if updates_clicked {
        app.launcher.settings_status = match app.check_for_updates_now() {
            Ok(status) => Some(status),
            Err(err) => Some(format!("Update check failed: {err}")),
        };
    }

    if let Some(status) = &app.launcher.settings_status {
        ui.add_space(8.0);
        ui.label(
            egui::RichText::new(status)
                .small()
                .color(egui::Color32::from_rgb(140, 140, 140)),
        );
    }

    if config_changed {
        app.request_settings_save();
    }
}

fn draw_group(
    ui: &mut Ui,
    title: &str,
    info: Option<&str>,
    add_contents: impl FnOnce(&mut Ui),
) {
    egui::Frame::none()
        .fill(egui::Color32::from_rgba_premultiplied(35, 35, 35, 179))
        .stroke(egui::Stroke::new(1.0, egui::Color32::from_rgb(51, 51, 51)))
        .inner_margin(egui::Margin::same(15.0))
        .show(ui, |ui| {
            ui.label(
                egui::RichText::new(format!("> {title}"))
                    .size(16.0)
                    .strong()
                    .color(egui::Color32::from_rgb(0, 242, 255)),
            );
            if let Some(info) = info {
                ui.add_space(2.0);
                ui.label(
                    egui::RichText::new(info)
                        .size(12.0)
                        .color(egui::Color32::from_rgb(136, 136, 136)),
                );
            }
            ui.add_space(6.0);
            add_contents(ui);
        });
}

fn draw_action_button(
    ui: &mut Ui,
    label: &str,
    size: [f32; 2],
    bg: egui::Color32,
    hover: egui::Color32,
    text: egui::Color32,
) -> bool {
    ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = bg;
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, bg);
        visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.0, text);
        visuals.widgets.hovered.bg_fill = hover;
        visuals.widgets.hovered.bg_stroke =
            egui::Stroke::new(1.0, egui::Color32::from_rgb(0, 242, 255));
        visuals.widgets.hovered.fg_stroke = egui::Stroke::new(1.0, egui::Color32::WHITE);
        ui.add_sized(size, egui::Button::new(label)).clicked()
    })
    .inner
}

fn path_label_sized(ui: &mut Ui, text: &str, width: f32) {
    egui::Frame::none()
        .fill(egui::Color32::from_rgb(5, 5, 5))
        .stroke(egui::Stroke::new(1.0, egui::Color32::from_rgb(51, 51, 51)))
        .inner_margin(egui::Margin::symmetric(12.0, 8.0))
        .show(ui, |ui| {
            ui.add_sized(
                [width.max(120.0), 20.0],
                egui::Label::new(
                    egui::RichText::new(text)
                        .monospace()
                        .color(egui::Color32::WHITE),
                ),
            );
        });
}

fn filename_from_path(value: &str) -> &str {
    std::path::Path::new(value)
        .file_name()
        .and_then(|part| part.to_str())
        .filter(|part| !part.trim().is_empty())
        .unwrap_or(value)
}

fn detect_ps2_path() -> Option<PathBuf> {
    let mut candidates = vec![
        PathBuf::from(r"C:\Program Files (x86)\Steam\steamapps\common\PlanetSide 2"),
        PathBuf::from(r"C:\Program Files\Steam\steamapps\common\PlanetSide 2"),
        PathBuf::from(r"C:\Users\Public\Daybreak Game Company\Installed Games\PlanetSide 2"),
    ];
    if let Ok(program_files_x86) = std::env::var("ProgramFiles(x86)") {
        candidates.push(
            Path::new(&program_files_x86)
                .join("Steam")
                .join("steamapps")
                .join("common")
                .join("PlanetSide 2"),
        );
    }
    if let Ok(program_files) = std::env::var("ProgramFiles") {
        candidates.push(
            Path::new(&program_files)
                .join("Steam")
                .join("steamapps")
                .join("common")
                .join("PlanetSide 2"),
        );
    }
    candidates
        .into_iter()
        .find(|path| path.exists() && path.is_dir())
}
