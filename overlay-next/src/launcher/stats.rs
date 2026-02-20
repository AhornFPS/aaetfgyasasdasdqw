use crate::app::OverlayState;
use eframe::egui::{self, Color32, RichText, Ui};

const GROUP_BG: Color32 = Color32::from_rgb(34, 34, 34);
const GROUP_BORDER: Color32 = Color32::from_rgb(51, 51, 51);

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    let mut config_changed = false;
    let mut move_toggle_clicked = false;
    let mut test_clicked = false;
    let mut save_clicked = false;

    let layout = &mut app.config.layout.stats;

    ui.add_space(8.0);

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("--- SESSION STATS WIDGET ---")
                .size(16.0)
                .strong()
                .color(crate::launcher::theme::COLOR_TEXT),
        );
        ui.add_space(8.0);

        let toggle_label = if app.config.show_session_stats {
            "STATS WIDGET: ON"
        } else {
            "STATS WIDGET: OFF"
        };
        if draw_tinted_button(
            ui,
            toggle_label,
            [220.0, 40.0],
            if app.config.show_session_stats {
                Color32::from_rgb(0, 68, 0)
            } else {
                Color32::from_rgb(68, 0, 0)
            },
            if app.config.show_session_stats {
                Color32::from_rgb(0, 85, 0)
            } else {
                Color32::from_rgb(85, 0, 0)
            },
            if app.config.show_session_stats {
                Color32::from_rgb(0, 255, 0)
            } else {
                Color32::from_rgb(255, 68, 68)
            },
            Color32::WHITE,
        ) {
            app.config.show_session_stats = !app.config.show_session_stats;
            app.stats_visible = app.config.show_session_stats;
            config_changed = true;
        }

        ui.add_space(8.0);
        ui.label(RichText::new("Text Adjust Number:").color(Color32::from_rgb(255, 204, 0)));

        draw_adjust_row(ui, "Text X (0=center):", &mut layout.tx, &mut config_changed);
        draw_adjust_row(ui, "Text Y (0=center):", &mut layout.ty, &mut config_changed);

        ui.add_space(6.0);
        ui.label(
            RichText::new("Visible Stats:")
                .strong()
                .color(Color32::from_rgb(255, 204, 0)),
        );

        ui.horizontal_wrapped(|ui| {
            ui.spacing_mut().item_spacing.x = 18.0;
            draw_green_checkbox(ui, &mut layout.show_k, "Kills", &mut config_changed);
            draw_green_checkbox(ui, &mut layout.show_d, "Deaths", &mut config_changed);
            draw_green_checkbox(ui, &mut layout.show_hsr, "HSR", &mut config_changed);
            draw_green_checkbox(ui, &mut layout.show_kpm, "KPM", &mut config_changed);
            draw_green_checkbox(ui, &mut layout.show_kph, "KPH", &mut config_changed);
            draw_green_checkbox(ui, &mut layout.show_time, "Time", &mut config_changed);
            draw_green_checkbox(ui, &mut layout.show_dhsr, "DHSR", &mut config_changed);
            draw_green_checkbox(ui, &mut layout.show_kd, "KD", &mut config_changed);
        });

        ui.add_space(8.0);
        ui.horizontal_wrapped(|ui| {
            ui.label("Font Size:");
            let mut font_size = normalize_font_size(&layout.font_name);
            egui::ComboBox::from_id_source("stats_font_size_combo")
                .selected_text(&font_size)
                .show_ui(ui, |ui| {
                    for value in ["8", "10", "12", "14", "16", "18", "20", "22", "24", "26", "28", "36", "48", "72", "100"] {
                        ui.selectable_value(&mut font_size, value.to_owned(), value);
                    }
                });
            if font_size != normalize_font_size(&layout.font_name) {
                layout.font_name = font_size;
                config_changed = true;
            }

            ui.add_space(8.0);
            ui.label("Label Color:");
            if draw_tinted_button(
                ui,
                "PICK",
                [70.0, 28.0],
                Color32::from_rgb(51, 51, 51),
                Color32::from_rgb(68, 68, 68),
                Color32::from_rgb(85, 85, 85),
                Color32::WHITE,
            ) {
                layout.label_color = Some("#00f2ff".to_owned());
                config_changed = true;
            }

            ui.label("Value Color:");
            if draw_tinted_button(
                ui,
                "PICK",
                [70.0, 28.0],
                Color32::from_rgb(51, 51, 51),
                Color32::from_rgb(68, 68, 68),
                Color32::from_rgb(85, 85, 85),
                Color32::WHITE,
            ) {
                layout.value_color = Some("#ffffff".to_owned());
                config_changed = true;
            }

            if ui
                .checkbox(
                    &mut layout.glow,
                    RichText::new("Stats Glow").color(Color32::from_rgb(0, 255, 0)),
                )
                .changed()
            {
                config_changed = true;
            }

            ui.label("Glow Color:");
            if draw_tinted_button(
                ui,
                "PICK",
                [70.0, 28.0],
                Color32::from_rgb(51, 51, 51),
                Color32::from_rgb(68, 68, 68),
                Color32::from_rgb(85, 85, 85),
                Color32::WHITE,
            ) {
                layout.glow_color = Some("#00f2ff".to_owned());
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

    if let Some(status) = &app.launcher.stats_status {
        ui.add_space(6.0);
        ui.label(status);
    }

    if config_changed {
        app.request_settings_save();
    }
    if move_toggle_clicked {
        app.toggle_overlay_move_mode();
    }
    if save_clicked {
        app.launcher.stats_status = match app.save_settings_now() {
            Ok(()) => Some("Stats settings saved.".to_owned()),
            Err(err) => Some(format!("Save failed: {err}")),
        };
    }
    if test_clicked {
        app.trigger_stats_test_ui();
    }
}

fn normalize_font_size(value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        "22".to_owned()
    } else if trimmed.parse::<u32>().is_ok() {
        trimmed.to_owned()
    } else {
        "22".to_owned()
    }
}

fn draw_adjust_row(ui: &mut Ui, label: &str, value: &mut f32, changed: &mut bool) {
    ui.horizontal(|ui| {
        ui.label(label);
        if ui
            .add_sized([260.0, 18.0], egui::Slider::new(value, -200.0..=200.0))
            .changed()
        {
            *changed = true;
        }
        ui.label(
            RichText::new(format!("{}", value.round() as i32))
                .color(Color32::from_rgb(0, 242, 255))
                .strong()
                .monospace(),
        );
    });
}

fn draw_green_checkbox(ui: &mut Ui, value: &mut bool, label: &str, changed: &mut bool) {
    if ui
        .checkbox(value, RichText::new(label).color(Color32::from_rgb(0, 255, 0)))
        .changed()
    {
        *changed = true;
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

        ui.add_sized(size, egui::Button::new(RichText::new(text).strong()))
            .clicked()
    })
    .inner
}
