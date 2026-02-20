use crate::app::OverlayState;
use eframe::egui::{self, Color32, RichText, Slider, Ui};

const GROUP_BG: Color32 = Color32::from_rgb(34, 34, 34);
const GROUP_BORDER: Color32 = Color32::from_rgb(51, 51, 51);

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    let mut config_changed = false;
    let mut move_toggle_clicked = false;
    let mut test_clicked = false;
    let mut save_clicked = false;
    let mut rec_path_clicked = false;

    let streak = &mut app.config.layout.streak;

    ui.add_space(6.0);

    ui.horizontal(|ui| {
        ui.label(
            RichText::new("KILLSTREAK SYSTEM")
                .size(16.0)
                .strong()
                .color(Color32::from_rgb(0, 242, 255)),
        );
        ui.add_space(ui.available_width());
    });

    ui.horizontal_wrapped(|ui| {
        if ui
            .checkbox(&mut streak.active, RichText::new("ENABLE KILLSTREAK SYSTEM").size(11.0).color(Color32::from_rgb(0, 255, 0)))
            .changed()
        {
            config_changed = true;
        }
        if ui
            .checkbox(&mut streak.anim_active, RichText::new("ENABLE PULSE ANIMATION").size(11.0).color(Color32::from_rgb(255, 204, 0)))
            .changed()
        {
            config_changed = true;
        }
        if ui
            .checkbox(&mut streak.streak_glow, RichText::new("ENABLE GLOW").size(11.0).color(Color32::from_rgb(0, 242, 255)))
            .changed()
        {
            config_changed = true;
        }

        ui.label(RichText::new("Glow Color:").size(11.0).color(Color32::from_rgb(221, 221, 221)));
        if draw_tinted_button(
            ui,
            "PICK",
            [70.0, 28.0],
            Color32::from_rgb(51, 51, 51),
            Color32::from_rgb(68, 68, 68),
            Color32::from_rgb(85, 85, 85),
            Color32::WHITE,
        ) {
            streak.glow_color = Some("#00f2ff".to_owned());
            config_changed = true;
        }
    });

    ui.add_space(8.0);

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("MAIN BACKGROUND & ANIMATION")
                .color(Color32::from_rgb(0, 242, 255))
                .strong()
                .size(11.0),
        );

        ui.horizontal(|ui| {
            ui.label("Main Image:");
            let mut filename = streak.filename.clone().unwrap_or_default();
            if ui
                .add_sized([ui.available_width() - 62.0, 26.0], egui::TextEdit::singleline(&mut filename))
                .changed()
            {
                streak.filename = if filename.trim().is_empty() {
                    None
                } else {
                    Some(filename.trim().to_owned())
                };
                config_changed = true;
            }
            if draw_tinted_button(
                ui,
                "...",
                [40.0, 26.0],
                Color32::from_rgb(51, 51, 51),
                Color32::from_rgb(68, 68, 68),
                Color32::from_rgb(85, 85, 85),
                Color32::WHITE,
            ) {
                if streak.filename.is_none() {
                    streak.filename = Some("KS_Counter.png".to_owned());
                    config_changed = true;
                }
            }
        });

        ui.horizontal(|ui| {
            ui.label("Pulse Speed:");
            if ui
                .add_sized(
                    [50.0, 24.0],
                    egui::DragValue::new(&mut streak.anim_speed).range(1.0..=300.0).speed(1.0),
                )
                .changed()
            {
                config_changed = true;
            }
            ui.label(
                RichText::new("(Higher = Faster)")
                    .size(10.0)
                    .italics()
                    .color(Color32::from_rgb(102, 102, 102)),
            );
        });
    });

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("FACTION KNIVES / ICONS (PNG)")
                .color(Color32::from_rgb(0, 242, 255))
                .strong()
                .size(11.0),
        );

        draw_knife_row(ui, "TR:", &mut streak.knife_tr, "Knife_TR_Large.png", &mut config_changed);
        draw_knife_row(ui, "NC:", &mut streak.knife_nc, "Knife_NC_Large.png", &mut config_changed);
        draw_knife_row(ui, "VS:", &mut streak.knife_vs, "Knife_VS_Large.png", &mut config_changed);
        draw_knife_row(ui, "NSO:", &mut streak.knife_nso, "knife.png", &mut config_changed);
    });

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("CUSTOM PATH RECORDING")
                .color(Color32::from_rgb(255, 140, 0))
                .strong()
                .size(11.0),
        );
        ui.label(
            RichText::new("1. Click 'REC PATH'. 2. Click points on screen. 3. Press SPACE to stop.")
                .size(10.0)
                .italics()
                .color(Color32::from_rgb(136, 136, 136)),
        );

        ui.horizontal(|ui| {
            if draw_tinted_button(
                ui,
                "REC PATH",
                [110.0, 32.0],
                Color32::from_rgb(136, 51, 0),
                Color32::from_rgb(170, 68, 0),
                Color32::from_rgb(255, 0, 0),
                Color32::WHITE,
            ) {
                rec_path_clicked = true;
                app.launcher.killstreak_status =
                    Some("Path edit armed: move the streak widget, then SAVE SETTINGS.".to_owned());
            }

            if draw_tinted_button(
                ui,
                "CLEAR PATH",
                [120.0, 32.0],
                Color32::from_rgb(51, 51, 51),
                Color32::from_rgb(68, 68, 68),
                Color32::from_rgb(85, 85, 85),
                Color32::from_rgb(238, 238, 238),
            ) {
                streak.knife_tr = None;
                streak.knife_nc = None;
                streak.knife_vs = None;
                streak.knife_nso = None;
                app.launcher.killstreak_status = Some("Knife paths cleared.".to_owned());
                config_changed = true;
            }
        });
    });

    let knives_label = if streak.show_knives {
        "KNIFE ICONS: ON"
    } else {
        "KNIFE ICONS: OFF"
    };
    if draw_tinted_button(
        ui,
        knives_label,
        [220.0, 35.0],
        if streak.show_knives {
            Color32::from_rgb(0, 68, 0)
        } else {
            Color32::from_rgb(68, 0, 0)
        },
        if streak.show_knives {
            Color32::from_rgb(0, 85, 0)
        } else {
            Color32::from_rgb(85, 0, 0)
        },
        if streak.show_knives {
            Color32::from_rgb(0, 255, 0)
        } else {
            Color32::from_rgb(255, 68, 68)
        },
        Color32::WHITE,
    ) {
        streak.show_knives = !streak.show_knives;
        config_changed = true;
    }

    ui.add_space(8.0);

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("POSITION & DESIGN")
                .color(Color32::from_rgb(0, 242, 255))
                .strong()
                .size(11.0),
        );

        ui.horizontal(|ui| {
            ui.label("Offset X:");
            if ui.add_sized([260.0, 18.0], Slider::new(&mut streak.x, -200.0..=200.0)).changed() {
                config_changed = true;
            }
        });

        ui.horizontal(|ui| {
            ui.label("Offset Y:");
            if ui.add_sized([260.0, 18.0], Slider::new(&mut streak.y, -200.0..=200.0)).changed() {
                config_changed = true;
            }
        });

        ui.horizontal(|ui| {
            ui.label("Scale:");
            if ui.add_sized([260.0, 18.0], Slider::new(&mut streak.scale, 0.1..=3.0)).changed() {
                config_changed = true;
            }
        });

        ui.horizontal(|ui| {
            ui.label("Style:");
            if draw_tinted_button(
                ui,
                "PICK",
                [70.0, 28.0],
                Color32::from_rgb(51, 51, 51),
                Color32::from_rgb(68, 68, 68),
                Color32::from_rgb(85, 85, 85),
                Color32::WHITE,
            ) {
                streak.color = "#00f2ff".to_owned();
                config_changed = true;
            }
            ui.label(RichText::new("Size:").size(11.0).color(Color32::from_rgb(221, 221, 221)));
            if ui
                .add_sized([140.0, 18.0], Slider::new(&mut streak.font_size, 10.0..=150.0))
                .changed()
            {
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
        if crate::launcher::theme::small_button(ui, "TEST").clicked() {
            test_clicked = true;
        }
        if crate::launcher::theme::success_button(ui, "SAVE SETTINGS").clicked() {
            save_clicked = true;
        }
    });

    if let Some(status) = &app.launcher.killstreak_status {
        ui.add_space(6.0);
        ui.label(status);
    }

    if config_changed {
        app.request_settings_save();
    }
    if move_toggle_clicked {
        app.toggle_overlay_move_mode();
    }
    if rec_path_clicked {
        app.set_overlay_move_mode(true);
    }
    if save_clicked {
        app.launcher.killstreak_status = match app.save_settings_now() {
            Ok(()) => Some("Killstreak settings saved.".to_owned()),
            Err(err) => Some(format!("Save failed: {err}")),
        };
    }
    if test_clicked {
        app.trigger_streak_test_ui();
    }
}

fn draw_group(ui: &mut Ui, add_contents: impl FnOnce(&mut Ui)) {
    egui::Frame::none()
        .fill(GROUP_BG)
        .stroke(egui::Stroke::new(1.0, GROUP_BORDER))
        .inner_margin(egui::Margin::same(8.0))
        .show(ui, |ui| add_contents(ui));
    ui.add_space(8.0);
}

fn draw_knife_row(
    ui: &mut Ui,
    label: &str,
    value: &mut Option<String>,
    default_name: &str,
    config_changed: &mut bool,
) {
    ui.horizontal(|ui| {
        ui.label(label);
        let mut text = value.clone().unwrap_or_default();
        if ui
            .add_sized([ui.available_width() - 62.0, 24.0], egui::TextEdit::singleline(&mut text))
            .changed()
        {
            *value = if text.trim().is_empty() {
                None
            } else {
                Some(text.trim().to_owned())
            };
            *config_changed = true;
        }

        if draw_tinted_button(
            ui,
            "...",
            [40.0, 24.0],
            Color32::from_rgb(51, 51, 51),
            Color32::from_rgb(68, 68, 68),
            Color32::from_rgb(85, 85, 85),
            Color32::WHITE,
        ) {
            if value.is_none() {
                *value = Some(default_name.to_owned());
                *config_changed = true;
            }
        }
    });
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
            egui::Button::new(RichText::new(text).strong().size(12.0)),
        )
        .clicked()
    })
    .inner
}
