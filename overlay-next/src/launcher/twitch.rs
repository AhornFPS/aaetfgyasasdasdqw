use crate::app::OverlayState;
use eframe::egui::{self, Color32, RichText, TextEdit, Ui};

const GROUP_BG: Color32 = Color32::from_rgb(34, 34, 34);
const GROUP_BORDER: Color32 = Color32::from_rgb(51, 51, 51);

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    let mut config_changed = false;
    let mut test_msg_clicked = false;

    if app.launcher.twitch.ignore_users_input.is_empty() && !app.config.twitch_ignore_users.is_empty() {
        app.launcher.twitch.ignore_users_input = app.config.twitch_ignore_users.join(", ");
    }
    if app.launcher.twitch.silence_sound_input.is_empty() {
        app.launcher.twitch.silence_sound_input = app
            .config
            .twitch_silence_sound_active
            .clone()
            .unwrap_or_default();
    }

    ui.add_space(6.0);

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("TWITCH CHAT OVERLAY")
                .size(20.0)
                .strong()
                .color(crate::launcher::theme::COLOR_TEXT),
        );
        ui.add_space(8.0);
        let toggle_label = if app.config.twitch_worker_enabled {
            "TWITCH CHAT: ON"
        } else {
            "TWITCH CHAT: OFF"
        };
        let toggle_clicked = if app.config.twitch_worker_enabled {
            draw_tinted_button(
                ui,
                toggle_label,
                [220.0, 40.0],
                Color32::from_rgb(0, 68, 0),
                Color32::from_rgb(0, 85, 0),
                Color32::from_rgb(0, 255, 0),
                Color32::WHITE,
            )
        } else {
            draw_tinted_button(
                ui,
                toggle_label,
                [220.0, 40.0],
                Color32::from_rgb(68, 0, 0),
                Color32::from_rgb(85, 0, 0),
                Color32::from_rgb(255, 68, 68),
                Color32::WHITE,
            )
        };
        if toggle_clicked {
            app.config.twitch_worker_enabled = !app.config.twitch_worker_enabled;
            if !app.config.twitch_worker_enabled {
                app.launcher.twitch.connected = false;
            }
            config_changed = true;
        }
    });

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("Channel Name (e.g. 'shroud'):")
                .size(12.0)
                .color(Color32::from_rgb(140, 140, 140)),
        );

        ui.horizontal(|ui| {
            let mut channel = app.config.twitch_channel.clone().unwrap_or_default();
            let channel_response = ui.add_sized(
                [ui.available_width() - 220.0, 28.0],
                TextEdit::singleline(&mut channel).hint_text("Enter Twitch channel name..."),
            );
            if channel_response.changed() {
                app.config.twitch_channel = if channel.trim().is_empty() {
                    None
                } else {
                    Some(channel.trim().to_owned())
                };
                config_changed = true;
            }

            let always_label = if app.config.twitch_always_on {
                "ALWAYS ON"
            } else {
                "ALWAYS OFF"
            };
            if draw_tinted_button(
                ui,
                always_label,
                [100.0, 30.0],
                if app.config.twitch_always_on {
                    Color32::from_rgb(0, 68, 0)
                } else {
                    Color32::from_rgb(68, 0, 0)
                },
                if app.config.twitch_always_on {
                    Color32::from_rgb(0, 85, 0)
                } else {
                    Color32::from_rgb(85, 0, 0)
                },
                if app.config.twitch_always_on {
                    Color32::from_rgb(0, 255, 0)
                } else {
                    Color32::from_rgb(255, 68, 68)
                },
                Color32::WHITE,
            ) {
                app.config.twitch_always_on = !app.config.twitch_always_on;
                config_changed = true;
            }

            if draw_tinted_button(
                ui,
                "CONNECT",
                [100.0, 30.0],
                Color32::from_rgb(100, 65, 165),
                Color32::from_rgb(117, 82, 182),
                Color32::from_rgb(169, 112, 255),
                Color32::WHITE,
            ) {
                app.start_twitch_connection();
            }
        });
    });

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("Ignore Users (comma separated):")
                .size(12.0)
                .color(Color32::from_rgb(140, 140, 140)),
        );
        if ui
            .add_sized(
                [ui.available_width(), 28.0],
                TextEdit::singleline(&mut app.launcher.twitch.ignore_users_input)
                    .hint_text("e.g. Nightbot, StreamElements, user123..."),
            )
            .changed()
        {
            app.config.twitch_ignore_users = app
                .launcher
                .twitch
                .ignore_users_input
                .split(',')
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .map(ToOwned::to_owned)
                .collect();
            config_changed = true;
        }

        let ignore_special_label = if app.config.twitch_ignore_special {
            "IGNORE SPECIAL CHARS (!): ON"
        } else {
            "IGNORE SPECIAL CHARS (!): OFF"
        };
        if draw_tinted_button(
            ui,
            ignore_special_label,
            [270.0, 30.0],
            if app.config.twitch_ignore_special {
                Color32::from_rgb(0, 68, 0)
            } else {
                Color32::from_rgb(68, 0, 0)
            },
            if app.config.twitch_ignore_special {
                Color32::from_rgb(0, 85, 0)
            } else {
                Color32::from_rgb(85, 0, 0)
            },
            if app.config.twitch_ignore_special {
                Color32::from_rgb(0, 255, 0)
            } else {
                Color32::from_rgb(255, 68, 68)
            },
            Color32::WHITE,
        ) {
            app.config.twitch_ignore_special = !app.config.twitch_ignore_special;
            config_changed = true;
        }
    });

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("APPEARANCE")
                .color(Color32::from_rgb(0, 242, 255))
                .strong(),
        );
        ui.add_space(6.0);

        ui.horizontal(|ui| {
            ui.label("Background Opacity:");
            if ui
                .add_sized(
                    [280.0, 20.0],
                    egui::Slider::new(&mut app.config.twitch_overlay_opacity, 0..=100),
                )
                .changed()
            {
                config_changed = true;
            }
        });

        ui.horizontal(|ui| {
            ui.label("Font Size:");
            let mut font_txt = app.config.twitch_font_size.to_string();
            egui::ComboBox::from_id_source("twitch_font_combo")
                .selected_text(&font_txt)
                .width(60.0)
                .show_ui(ui, |ui| {
                    for value in ["10", "12", "14", "16", "18", "20", "24"] {
                        ui.selectable_value(&mut font_txt, value.to_owned(), value);
                    }
                });
            if let Ok(size) = font_txt.parse::<u32>() {
                if size != app.config.twitch_font_size {
                    app.config.twitch_font_size = size;
                    config_changed = true;
                }
            }
        });

        ui.horizontal(|ui| {
            ui.label("Position X / Y:");
            if ui
                .add_sized(
                    [160.0, 20.0],
                    egui::Slider::new(&mut app.config.twitch_overlay_x, 0..=1920),
                )
                .changed()
            {
                config_changed = true;
            }
            if ui
                .add_sized(
                    [160.0, 20.0],
                    egui::Slider::new(&mut app.config.twitch_overlay_y, 0..=1080),
                )
                .changed()
            {
                config_changed = true;
            }
        });

        ui.horizontal(|ui| {
            ui.label("Size W / H:");
            if ui
                .add_sized(
                    [160.0, 20.0],
                    egui::Slider::new(&mut app.config.twitch_overlay_width, 200..=800),
                )
                .changed()
            {
                config_changed = true;
            }
            if ui
                .add_sized(
                    [160.0, 20.0],
                    egui::Slider::new(&mut app.config.twitch_overlay_height, 200..=1000),
                )
                .changed()
            {
                config_changed = true;
            }
        });

        ui.horizontal(|ui| {
            ui.label("Hold Text for (s):");
            let mut hold = app.config.chat_hold_seconds.round().clamp(0.0, 600.0) as u64;
            if ui
                .add(
                    egui::DragValue::new(&mut hold)
                        .range(0..=600)
                        .speed(1)
                        .suffix(" s (0 = Permanent)"),
                )
                .changed()
            {
                app.config.chat_hold_seconds = hold as f32;
                config_changed = true;
            }
        });
    });

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("SILENCE ALERT")
                .size(16.0)
                .strong()
                .color(crate::launcher::theme::COLOR_TEXT),
        );
        ui.label(
            RichText::new("Plays a sound if no message is received for a certain time.")
                .size(12.0)
                .color(Color32::from_rgb(140, 140, 140)),
        );

        if ui
            .checkbox(&mut app.config.twitch_silence_alert_active, "Enable Silence Alert")
            .changed()
        {
            config_changed = true;
        }

        ui.horizontal(|ui| {
            ui.label("Silence Timeout (s):");
            if ui
                .add(
                    egui::DragValue::new(&mut app.config.twitch_silence_timeout_secs)
                        .range(5..=86400)
                        .speed(1),
                )
                .changed()
            {
                config_changed = true;
            }
            ui.add_space(ui.available_width());
        });

        ui.horizontal(|ui| {
            ui.label("Alert Sound:");
            if ui
                .add_sized(
                    [ui.available_width() - 170.0, 28.0],
                    TextEdit::singleline(&mut app.launcher.twitch.silence_sound_input)
                        .hint_text("No file selected"),
                )
                .changed()
            {
                let trimmed = app.launcher.twitch.silence_sound_input.trim().to_owned();
                app.config.twitch_silence_sound_active = if trimmed.is_empty() {
                    None
                } else {
                    Some(trimmed.clone())
                };
                if !trimmed.is_empty() && !app.config.twitch_silence_sounds.contains(&trimmed) {
                    app.config.twitch_silence_sounds.push(trimmed);
                }
                config_changed = true;
            }

            if draw_tinted_button(
                ui,
                "...",
                [40.0, 28.0],
                Color32::from_rgb(51, 51, 51),
                Color32::from_rgb(68, 68, 68),
                Color32::from_rgb(85, 85, 85),
                Color32::WHITE,
            ) {
                if app.launcher.twitch.silence_sound_input.trim().is_empty() {
                    app.launcher.twitch.silence_sound_input = "ding-sound-effect_2.ogg".to_owned();
                    if !app
                        .config
                        .twitch_silence_sounds
                        .contains(&app.launcher.twitch.silence_sound_input)
                    {
                        app.config
                            .twitch_silence_sounds
                            .push(app.launcher.twitch.silence_sound_input.clone());
                    }
                    app.config.twitch_silence_sound_active =
                        Some(app.launcher.twitch.silence_sound_input.clone());
                    config_changed = true;
                }
            }

            if draw_tinted_button(
                ui,
                "DEL",
                [40.0, 28.0],
                Color32::from_rgb(68, 0, 0),
                Color32::from_rgb(85, 0, 0),
                Color32::from_rgb(255, 68, 68),
                Color32::WHITE,
            ) {
                let active = app.launcher.twitch.silence_sound_input.trim().to_owned();
                if !active.is_empty() {
                    app.config.twitch_silence_sounds.retain(|item| item != &active);
                }
                app.launcher.twitch.silence_sound_input.clear();
                app.config.twitch_silence_sound_active = None;
                config_changed = true;
            }
        });

        ui.horizontal(|ui| {
            ui.label("Volume:");
            if ui
                .add_sized(
                    [280.0, 20.0],
                    egui::Slider::new(&mut app.config.twitch_silence_volume, 0..=100),
                )
                .changed()
            {
                config_changed = true;
            }
            ui.label(
                RichText::new(format!("{}%", app.config.twitch_silence_volume))
                    .strong()
                    .color(Color32::from_rgb(0, 242, 255)),
            );

            if draw_tinted_button(
                ui,
                "TEST",
                [80.0, 28.0],
                Color32::from_rgb(68, 68, 68),
                Color32::from_rgb(82, 82, 82),
                Color32::from_rgb(136, 136, 136),
                Color32::from_rgb(238, 238, 238),
            ) {
                let name = app.launcher.twitch.silence_sound_input.clone();
                app.launcher.twitch.status = match app
                    .play_audio_preview_by_name(&name, app.config.twitch_silence_volume)
                {
                    Ok(()) => Some(format!("Silence sound preview: {name}")),
                    Err(err) => Some(format!("Silence sound preview failed: {err}")),
                };
            }
        });
    });

    ui.horizontal(|ui| {
        let move_label = if app.launcher.overlay_move_mode {
            "STOP MOVE UI"
        } else {
            "MOVE UI"
        };
        if crate::launcher::theme::primary_button(ui, move_label).clicked() {
            app.toggle_overlay_move_mode();
        }
        if crate::launcher::theme::small_button(ui, "TEST MSG").clicked() {
            test_msg_clicked = true;
        }
        if crate::launcher::theme::success_button(ui, "SAVE SETTINGS").clicked() {
            app.launcher.twitch.status = match app.save_settings_now() {
                Ok(()) => Some("Twitch settings saved.".to_owned()),
                Err(err) => Some(format!("Save failed: {err}")),
            };
        }
    });

    if let Some(status) = &app.launcher.twitch.status {
        ui.label(status);
    }
    ui.label(if app.launcher.twitch.connected {
        "Connection State: CONNECTED"
    } else {
        "Connection State: DISCONNECTED"
    });

    if config_changed {
        app.request_settings_save();
    }
    if test_msg_clicked {
        app.trigger_twitch_test_msg();
    }
}

fn draw_group(ui: &mut Ui, add_contents: impl FnOnce(&mut Ui)) {
    egui::Frame::none()
        .fill(GROUP_BG)
        .stroke(egui::Stroke::new(1.0, GROUP_BORDER))
        .inner_margin(egui::Margin::same(10.0))
        .show(ui, |ui| add_contents(ui));
    ui.add_space(10.0);
}

fn draw_tinted_button(
    ui: &mut Ui,
    text: &str,
    size: [f32; 2],
    bg: Color32,
    hover: Color32,
    border: Color32,
    fg: Color32,
) -> bool {
    ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = bg;
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, border);
        visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.0, fg);

        visuals.widgets.hovered.bg_fill = hover;
        visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, border);
        visuals.widgets.hovered.fg_stroke = egui::Stroke::new(1.0, Color32::WHITE);

        visuals.widgets.active.bg_fill = bg;
        visuals.widgets.active.bg_stroke = egui::Stroke::new(1.0, border);

        ui.add_sized(
            size,
            egui::Button::new(RichText::new(text).strong().size(13.0)),
        )
        .clicked()
    })
    .inner
}
