use eframe::egui::{self, Align, Color32, Layout, RichText, Ui};

use crate::app::OverlayState;

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    let mut init_high = false;
    let mut init_low = false;
    let mut open_settings_editor = false;

    ui.spacing_mut().item_spacing.y = 30.0;
    let is_wide = ui.available_width() >= 900.0;
    if is_wide {
        let spacing = 25.0;
        let card_width = ((ui.available_width() - spacing) / 2.0).max(280.0);
        ui.horizontal_top(|ui| {
            ui.spacing_mut().item_spacing.x = spacing;
            init_high |= draw_profile_card(
                ui,
                card_width,
                "HIGH SETTINGS",
                "VEHICLE",
                "Load High Fidelity Assets & Maximum Visual Range. Perfect for pilots and tankers.",
                Color32::from_rgb(0, 102, 0),
            );
            init_low |= draw_profile_card(
                ui,
                card_width,
                "LOW SETTINGS",
                "INFANTRY",
                "Disable Shadows & Particles for Peak Framerates. Optimized for competitive infantry play.",
                Color32::from_rgb(102, 0, 0),
            );
        });
    } else {
        let width = ui.available_width().max(280.0);
        init_high |= draw_profile_card(
            ui,
            width,
            "HIGH SETTINGS",
            "VEHICLE",
            "Load High Fidelity Assets & Maximum Visual Range. Perfect for pilots and tankers.",
            Color32::from_rgb(0, 102, 0),
        );
        init_low |= draw_profile_card(
            ui,
            width,
            "LOW SETTINGS",
            "INFANTRY",
            "Disable Shadows & Particles for Peak Framerates. Optimized for competitive infantry play.",
            Color32::from_rgb(102, 0, 0),
        );
    }
    ui.add_space(10.0);

    let settings_clicked = ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = Color32::from_rgb(34, 34, 34);
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, Color32::from_rgb(68, 68, 68));
        visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.0, Color32::from_rgb(136, 136, 136));
        visuals.widgets.hovered.bg_fill = Color32::from_rgb(51, 51, 51);
        visuals.widgets.hovered.bg_stroke =
            egui::Stroke::new(1.0, Color32::from_rgb(0, 242, 255));
        visuals.widgets.hovered.fg_stroke = egui::Stroke::new(1.0, Color32::WHITE);
        ui.add_sized([220.0, 36.0], egui::Button::new("SETTINGS EDITOR"))
            .clicked()
    }).inner;
    if settings_clicked {
        open_settings_editor = true;
    }

    ui.add_space(6.0);
    ui.horizontal_centered(|ui| {
        let footer = app
            .launcher
            .launcher_status
            .as_deref()
            .unwrap_or("STATUS: SYSTEM_READY | INTEGRITY: OPTIMAL");
        ui.label(
            RichText::new(footer)
                .size(11.0)
                .color(Color32::from_rgb(74, 106, 122)),
        );
    });

    if init_high {
        app.launcher.launcher_status = match app.initialize_ps2_user_options(true) {
            Ok(path) => Some(format!(
                "Applied HIGH settings profile to {}",
                path.display()
            )),
            Err(err) => Some(format!("Initialize HIGH failed: {err}")),
        };
    }
    if init_low {
        app.launcher.launcher_status = match app.initialize_ps2_user_options(false) {
            Ok(path) => Some(format!(
                "Applied LOW settings profile to {}",
                path.display()
            )),
            Err(err) => Some(format!("Initialize LOW failed: {err}")),
        };
    }
    if open_settings_editor {
        app.launcher.launcher_status = match app.launch_ps2_settings_editor() {
            Ok(()) => Some("Opened PS2 settings editor.".to_owned()),
            Err(err) => Some(format!("Open settings editor failed: {err}")),
        };
    }
}

fn draw_profile_card(
    ui: &mut Ui,
    width: f32,
    title: &str,
    subtitle: &str,
    description: &str,
    accent: Color32,
) -> bool {
    let mut clicked = false;
    ui.allocate_ui_with_layout(
        egui::vec2(width, 0.0),
        Layout::top_down(Align::Min),
        |ui| {
            egui::Frame::none()
                .fill(Color32::from_rgba_premultiplied(30, 30, 30, 179))
                .stroke(egui::Stroke::new(1.0, Color32::from_rgb(51, 51, 51)))
                .inner_margin(egui::Margin::same(25.0))
                .show(ui, |ui| {
                    ui.set_min_height(320.0);
                    ui.spacing_mut().item_spacing.y = 15.0;
                    ui.label(
                        RichText::new(format!("[ {subtitle} ]"))
                            .monospace()
                            .strong()
                            .color(accent),
                    );
                    ui.label(
                        RichText::new(title)
                            .size(24.0)
                            .strong()
                            .color(Color32::WHITE),
                    );
                    ui.add_sized(
                        [ui.available_width(), 66.0],
                        egui::Label::new(
                            RichText::new(description)
                                .size(13.0)
                                .color(Color32::from_rgb(170, 170, 170)),
                        )
                        .wrap(),
                    );
                    ui.add_space(10.0);
                    clicked = ui
                        .scope(|ui| {
                            let visuals = &mut ui.style_mut().visuals;
                            visuals.widgets.inactive.bg_fill = accent;
                            visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, accent);
                            visuals.widgets.inactive.fg_stroke =
                                egui::Stroke::new(1.0, Color32::from_rgb(220, 220, 220));
                            visuals.widgets.hovered.bg_fill = lighten(accent, 0.15);
                            visuals.widgets.hovered.bg_stroke =
                                egui::Stroke::new(1.0, Color32::WHITE);
                            visuals.widgets.active.bg_fill = darken(accent, 0.2);
                            ui.add_sized(
                                [ui.available_width(), 44.0],
                                egui::Button::new(
                                    RichText::new(format!("INITIALIZE: {title}"))
                                        .strong()
                                        .size(14.0),
                                ),
                            )
                            .clicked()
                        })
                        .inner;
                });
        },
    );
    clicked
}

fn lighten(color: Color32, amount: f32) -> Color32 {
    let t = amount.clamp(0.0, 1.0);
    let lerp = |c: u8| ((c as f32) + (255.0 - c as f32) * t).round().clamp(0.0, 255.0) as u8;
    Color32::from_rgba_premultiplied(lerp(color.r()), lerp(color.g()), lerp(color.b()), color.a())
}

fn darken(color: Color32, amount: f32) -> Color32 {
    let t = (1.0 - amount.clamp(0.0, 1.0)).max(0.0);
    let scale = |c: u8| ((c as f32) * t).round().clamp(0.0, 255.0) as u8;
    Color32::from_rgba_premultiplied(
        scale(color.r()),
        scale(color.g()),
        scale(color.b()),
        color.a(),
    )
}
