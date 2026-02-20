use crate::app::OverlayState;
use eframe::egui::{self, Color32, RichText, Ui};

const GROUP_BG: Color32 = Color32::from_rgb(34, 34, 34);
const GROUP_BORDER: Color32 = Color32::from_rgb(51, 51, 51);

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    let mut config_changed = false;
    let mut test_clicked = false;
    let mut save_clicked = false;
    let mut move_toggle_clicked = false;

    ui.add_space(8.0);

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("--- KILLFEED ---")
                .size(16.0)
                .strong()
                .color(Color32::from_rgb(255, 68, 68)),
        );
        ui.add_space(8.0);

        let toggle_label = if app.config.show_killfeed {
            "KILLFEED: ON"
        } else {
            "KILLFEED: OFF"
        };
        if draw_tinted_button(
            ui,
            toggle_label,
            [210.0, 40.0],
            if app.config.show_killfeed {
                Color32::from_rgb(0, 68, 0)
            } else {
                Color32::from_rgb(68, 0, 0)
            },
            if app.config.show_killfeed {
                Color32::from_rgb(0, 85, 0)
            } else {
                Color32::from_rgb(85, 0, 0)
            },
            if app.config.show_killfeed {
                Color32::from_rgb(0, 255, 0)
            } else {
                Color32::from_rgb(255, 68, 68)
            },
            Color32::WHITE,
        ) {
            app.config.show_killfeed = !app.config.show_killfeed;
            config_changed = true;
        }

        ui.add_space(8.0);
        ui.label(
            RichText::new("Headshot Icon (PNG):")
                .size(12.0)
                .color(Color32::from_rgb(140, 140, 140)),
        );
        ui.horizontal(|ui| {
            let mut hs_icon = app.config.feed_headshot_icon.clone().unwrap_or_default();
            if ui
                .add_sized(
                    [ui.available_width() - 62.0, 28.0],
                    egui::TextEdit::singleline(&mut hs_icon),
                )
                .changed()
            {
                app.config.feed_headshot_icon = if hs_icon.trim().is_empty() {
                    None
                } else {
                    Some(hs_icon.trim().to_owned())
                };
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
                if app.config.feed_headshot_icon.is_none() {
                    app.config.feed_headshot_icon = Some("Headshot_Icon.png".to_owned());
                    config_changed = true;
                }
            }
        });

        if ui
            .checkbox(
                &mut app.config.feed_show_revives,
                RichText::new("Show Revives in Feed").color(Color32::from_rgb(0, 255, 0)),
            )
            .changed()
        {
            config_changed = true;
        }
        if ui
            .checkbox(
                &mut app.config.feed_show_gunner,
                RichText::new("Show Gunner Kills in Feed").color(Color32::from_rgb(0, 255, 0)),
            )
            .changed()
        {
            config_changed = true;
        }
        if ui
            .checkbox(
                &mut app.config.feed_show_vehicle,
                RichText::new("Show Vehicle Kills in Feed").color(Color32::from_rgb(0, 255, 0)),
            )
            .changed()
        {
            config_changed = true;
        }

        ui.horizontal(|ui| {
            if ui
                .checkbox(
                    &mut app.config.feed_auto_remove,
                    RichText::new("Auto-remove feed lines").color(Color32::from_rgb(0, 255, 0)),
                )
                .changed()
            {
                config_changed = true;
            }
            ui.add_space(12.0);
            ui.label(RichText::new("Stay (sec):").color(Color32::from_rgb(221, 221, 221)));
            if ui
                .add(
                    egui::DragValue::new(&mut app.config.feed_hold_seconds)
                        .range(1..=600)
                        .speed(1),
                )
                .changed()
            {
                config_changed = true;
            }
        });

        ui.horizontal(|ui| {
            ui.label("Feed Font Size:");
            let mut feed_font_size = normalize_feed_font_size(&app.config.feed_font_name);
            egui::ComboBox::from_id_source("feed_font_size_combo")
                .selected_text(&feed_font_size)
                .show_ui(ui, |ui| {
                    for value in ["8", "10", "12", "14", "16", "18", "19", "20", "22", "24", "26", "28", "36", "48", "72", "100"] {
                        ui.selectable_value(&mut feed_font_size, value.to_owned(), value);
                    }
                });
            if feed_font_size != normalize_feed_font_size(&app.config.feed_font_name) {
                app.config.feed_font_name = feed_font_size;
                config_changed = true;
            }

            ui.label("Icon Size:");
            let mut hs_px = headshot_scale_to_px(app.config.feed_headshot_scale);
            egui::ComboBox::from_id_source("feed_hs_px_combo")
                .selected_text(&hs_px)
                .width(60.0)
                .show_ui(ui, |ui| {
                    for value in ["16", "19", "24", "28", "32", "36", "48", "64", "72", "80", "100"] {
                        ui.selectable_value(&mut hs_px, value.to_owned(), value);
                    }
                });
            let parsed_scale = px_to_headshot_scale(&hs_px);
            if (parsed_scale - app.config.feed_headshot_scale).abs() > f32::EPSILON {
                app.config.feed_headshot_scale = parsed_scale;
                config_changed = true;
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
            move_toggle_clicked = true;
        }
        if crate::launcher::theme::small_button(ui, "TEST UI").clicked() {
            test_clicked = true;
        }
        if crate::launcher::theme::success_button(ui, "SAVE SETTINGS").clicked() {
            save_clicked = true;
        }
    });

    if config_changed {
        app.request_settings_save();
    }
    if move_toggle_clicked {
        app.toggle_overlay_move_mode();
    }
    if save_clicked {
        let _ = app.save_settings_now();
    }
    if test_clicked {
        app.trigger_killfeed_test_ui();
    }
}

fn normalize_feed_font_size(value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.parse::<u32>().is_ok() {
        trimmed.to_owned()
    } else {
        "19".to_owned()
    }
}

fn headshot_scale_to_px(scale: f32) -> String {
    let px = (scale * 19.0).round().clamp(16.0, 100.0) as i32;
    px.to_string()
}

fn px_to_headshot_scale(px: &str) -> f32 {
    px.parse::<f32>()
        .map(|value| (value / 19.0).clamp(0.5, 5.5))
        .unwrap_or(1.0)
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

        ui.add_sized(size, egui::Button::new(RichText::new(text).strong()))
            .clicked()
    })
    .inner
}
