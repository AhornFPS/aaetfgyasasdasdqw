use crate::app::OverlayState;
use eframe::egui::{self, Color32, RichText, TextEdit, Ui};

const GROUP_BG: Color32 = Color32::from_rgb(34, 34, 34);
const GROUP_BORDER: Color32 = Color32::from_rgb(51, 51, 51);

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    let mut config_changed = false;

    if app.launcher.obs.service_enabled != app.config.obs_service_enabled {
        app.launcher.obs.service_enabled = app.config.obs_service_enabled;
    }
    if app.launcher.obs.http_port != app.config.obs_http_port {
        app.launcher.obs.http_port = app.config.obs_http_port;
    }
    if app.launcher.obs.ws_port != app.config.obs_ws_port {
        app.launcher.obs.ws_port = app.config.obs_ws_port;
    }
    if app.launcher.obs.http_port_input.trim().is_empty() {
        app.launcher.obs.http_port_input = app.launcher.obs.http_port.to_string();
    }
    if app.launcher.obs.ws_port_input.trim().is_empty() {
        app.launcher.obs.ws_port_input = app.launcher.obs.ws_port.to_string();
    }

    ui.add_space(8.0);
    ui.label(
        RichText::new("OBS STUDIO INTEGRATION")
            .size(22.0)
            .strong()
            .color(crate::launcher::theme::COLOR_TEXT),
    );
    ui.add_space(12.0);

    draw_group(ui, |ui| {
        let service_label = if app.launcher.obs.service_enabled {
            "OBS SERVICE: ON"
        } else {
            "OBS SERVICE: OFF"
        };

        let service_clicked = if app.launcher.obs.service_enabled {
            draw_tinted_button(
                ui,
                service_label,
                [220.0, 45.0],
                Color32::from_rgb(0, 68, 0),
                Color32::from_rgb(0, 85, 0),
                Color32::from_rgb(0, 255, 0),
                Color32::WHITE,
            )
        } else {
            draw_tinted_button(
                ui,
                service_label,
                [220.0, 45.0],
                Color32::from_rgb(68, 0, 0),
                Color32::from_rgb(85, 0, 0),
                Color32::from_rgb(255, 68, 68),
                Color32::WHITE,
            )
        };

        if service_clicked {
            app.launcher.obs.service_enabled = !app.launcher.obs.service_enabled;
            app.config.obs_service_enabled = app.launcher.obs.service_enabled;
            config_changed = true;
        }

        ui.add_space(10.0);
        ui.horizontal(|ui| {
            ui.label(RichText::new("HTTP Port:").color(Color32::from_rgb(187, 187, 187)));
            let http_resp = ui.add_sized(
                [80.0, 28.0],
                TextEdit::singleline(&mut app.launcher.obs.http_port_input),
            );
            if http_resp.changed() {
                if let Some(parsed) = parse_port(&app.launcher.obs.http_port_input) {
                    app.launcher.obs.http_port = parsed;
                    app.config.obs_http_port = parsed;
                    config_changed = true;
                }
            }

            ui.add_space(12.0);
            ui.label(RichText::new("WS Port:").color(Color32::from_rgb(187, 187, 187)));
            let ws_resp = ui.add_sized(
                [80.0, 28.0],
                TextEdit::singleline(&mut app.launcher.obs.ws_port_input),
            );
            if ws_resp.changed() {
                if let Some(parsed) = parse_port(&app.launcher.obs.ws_port_input) {
                    app.launcher.obs.ws_port = parsed;
                    app.config.obs_ws_port = parsed;
                    config_changed = true;
                }
            }

            ui.add_space(ui.available_width());
        });
    });

    draw_group(ui, |ui| {
        ui.label(
            RichText::new(
                "If you capture Planetside with game capture, use the Browser Source method.\nThis renders the overlay via a local web server.",
            )
            .color(Color32::from_rgb(204, 204, 204))
            .size(13.0),
        );
    });

    draw_group(ui, |ui| {
        ui.horizontal(|ui| {
            let http_port_for_url = parse_port(&app.launcher.obs.http_port_input)
                .map(|value| value.to_string())
                .unwrap_or_else(|| app.launcher.obs.http_port.to_string());
            let url = format!("http://localhost:{http_port_for_url}/");

            ui.label(
                RichText::new(&url)
                    .size(18.0)
                    .strong()
                    .color(Color32::from_rgb(0, 255, 0))
                    .monospace(),
            );
            if draw_tinted_button(
                ui,
                "COPY URL",
                [110.0, 34.0],
                Color32::from_rgb(0, 68, 0),
                Color32::from_rgb(0, 102, 0),
                Color32::from_rgb(0, 255, 0),
                Color32::from_rgb(0, 102, 0),
            ) {
                ui.ctx().copy_text(url);
                app.launcher.obs.copy_feedback = Some("COPIED!".to_owned());
            }
        });
        if let Some(text) = &app.launcher.obs.copy_feedback {
            ui.label(RichText::new(text).color(Color32::from_rgb(0, 242, 255)).strong());
        }
    });

    draw_group(ui, |ui| {
        ui.label(
            RichText::new("SETUP INSTRUCTIONS:")
                .color(Color32::from_rgb(0, 242, 255))
                .strong()
                .size(14.0),
        );

        for line in [
            "1. Open OBS Studio.",
            "2. Add a new Source: Browser.",
            "3. Uncheck 'Local file'.",
            "4. Paste the URL above into the URL field.",
            "5. Set Width and Height to your screen resolution.",
            "6. Check 'Refresh browser when scene becomes active'.",
            "7. Click OK.",
            "Note: If localhost does not work, try 127.0.0.1 instead.",
        ] {
            ui.label(RichText::new(line).color(Color32::from_rgb(221, 221, 221)).size(13.0));
        }
    });

    if config_changed {
        app.request_settings_save();
    }
}

fn parse_port(value: &str) -> Option<u16> {
    value
        .trim()
        .parse::<u16>()
        .ok()
        .filter(|port| *port > 0)
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
            egui::Button::new(RichText::new(text).strong().size(14.0)),
        )
        .clicked()
    })
    .inner
}
