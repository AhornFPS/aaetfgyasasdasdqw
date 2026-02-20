use eframe::egui::{self, Color32, Context, Frame, RichText, Style, Ui, Visuals};

pub const COLOR_BG: Color32 = Color32::from_rgb(17, 17, 17); // #111111
pub const COLOR_PANEL: Color32 = Color32::from_rgb(17, 17, 17); // #111111
pub const COLOR_ACCENT: Color32 = Color32::from_rgb(0, 242, 255); // #00f2ff
pub const COLOR_TEXT: Color32 = Color32::from_rgb(220, 220, 220);
pub const COLOR_BORDER: Color32 = Color32::from_rgb(51, 51, 51); // #333333
pub const COLOR_TAB_BG: Color32 = Color32::from_rgb(34, 34, 34); // #222222
pub const COLOR_TAB_BG_ACTIVE: Color32 = Color32::from_rgb(30, 30, 30); // #1e1e1e
pub const COLOR_CARD_BG: Color32 = Color32::from_rgb(22, 22, 22);
pub const COLOR_GREEN: Color32 = Color32::from_rgb(0, 160, 0);
pub const COLOR_RED: Color32 = Color32::from_rgb(156, 30, 30);
pub const COLOR_BLUE: Color32 = Color32::from_rgb(16, 98, 164);

pub fn apply_theme(ctx: &Context) {
    let mut style = Style::default();
    let mut visuals = Visuals::dark();

    // Backgrounds
    visuals.window_fill = COLOR_BG;
    visuals.panel_fill = COLOR_PANEL;

    // Widgets
    visuals.widgets.noninteractive.bg_fill = COLOR_PANEL;
    visuals.widgets.noninteractive.fg_stroke = egui::Stroke::new(1.0, COLOR_TEXT);

    // Buttons (Inactive)
    visuals.widgets.inactive.bg_fill = Color32::from_rgb(34, 34, 34);
    visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.0, COLOR_TEXT);
    visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, COLOR_BORDER);
    visuals.widgets.inactive.weak_bg_fill = Color32::from_rgb(34, 34, 34);

    // Buttons (Hover)
    visuals.widgets.hovered.bg_fill = Color32::from_rgb(45, 45, 45); // #2d2d2d
    visuals.widgets.hovered.fg_stroke = egui::Stroke::new(1.0, Color32::WHITE);
    visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, Color32::from_rgb(90, 90, 90));
    visuals.widgets.hovered.expansion = 0.0;

    // Buttons (Active)
    visuals.widgets.active.bg_fill = Color32::from_rgb(0, 70, 78); // cyan-ish pressed
    visuals.widgets.active.fg_stroke = egui::Stroke::new(1.0, COLOR_ACCENT);
    visuals.widgets.active.bg_stroke = egui::Stroke::new(1.0, COLOR_ACCENT);

    // Selection
    visuals.selection.bg_fill = COLOR_ACCENT.linear_multiply(0.3);
    visuals.selection.stroke = egui::Stroke::new(1.0, COLOR_ACCENT);

    // Separators
    visuals.widgets.noninteractive.bg_stroke = egui::Stroke::new(1.0, COLOR_BORDER);

    style.visuals = visuals;

    // Spacing
    style.spacing.item_spacing = egui::vec2(10.0, 8.0);
    style.spacing.window_margin = egui::Margin::same(0.0);
    style.spacing.button_padding = egui::vec2(12.0, 8.0);
    style.spacing.interact_size.y = 30.0;

    ctx.set_style(style);
}

pub fn custom_tab_button(ui: &mut egui::Ui, text: &str, selected: bool) -> egui::Response {
    let desired_size = egui::vec2(ui.available_width(), 48.0);
    let (rect, response) = ui.allocate_exact_size(desired_size, egui::Sense::click());

    if ui.is_rect_visible(rect) {
        // Background
        if selected || response.hovered() {
            let bg_color = if selected {
                Color32::from_rgb(26, 26, 26) // #1a1a1a for selected
            } else {
                Color32::from_rgb(26, 26, 26) // Hover
            };

            // Gradient effect simulation (Egui plain fill for now)
            ui.painter().rect_filled(rect, 0.0, bg_color);
        }

        // Left Accent Border (Selected only)
        if selected {
            let border_rect = egui::Rect::from_min_size(rect.min, egui::vec2(4.0, rect.height()));
            ui.painter().rect_filled(border_rect, 0.0, COLOR_ACCENT);
        }

        // Text
        let text_color = if selected { COLOR_ACCENT } else { COLOR_TEXT };
        let font_id = egui::FontId::new(13.0, egui::FontFamily::Proportional);

        ui.painter().text(
            egui::pos2(rect.left() + 18.0, rect.center().y),
            egui::Align2::LEFT_CENTER,
            text.to_uppercase(),
            font_id,
            text_color,
        );

        // Bottom Border
        let bottom_line = egui::Shape::line_segment(
            [rect.left_bottom(), rect.right_bottom()],
            egui::Stroke::new(1.0, Color32::from_rgb(26, 26, 26)),
        );
        ui.painter().add(bottom_line);
    }

    response
}

pub fn top_nav_button(ui: &mut Ui, text: &str, selected: bool) -> egui::Response {
    let base = (text.len() as f32 * 7.0) + 26.0;
    let desired_size = egui::vec2(base.clamp(88.0, 170.0), 36.0);
    let (rect, response) = ui.allocate_exact_size(desired_size, egui::Sense::click());

    if ui.is_rect_visible(rect) {
        let bg = if selected {
            COLOR_TAB_BG_ACTIVE
        } else {
            COLOR_TAB_BG
        };
        let stroke = if selected {
            egui::Stroke::new(1.0, COLOR_ACCENT)
        } else {
            egui::Stroke::new(1.0, COLOR_BORDER)
        };
        ui.painter().rect(rect, 4.0, bg, stroke);
        if selected {
            let underline = egui::Rect::from_min_max(
                egui::pos2(rect.left() + 6.0, rect.bottom() - 3.0),
                egui::pos2(rect.right() - 6.0, rect.bottom() - 1.0),
            );
            ui.painter().rect_filled(underline, 1.0, COLOR_ACCENT);
        }
        ui.painter().text(
            rect.center(),
            egui::Align2::CENTER_CENTER,
            text.to_uppercase(),
            egui::FontId::new(12.0, egui::FontFamily::Proportional),
            if selected { COLOR_ACCENT } else { COLOR_TEXT },
        );
    }
    response
}

pub fn section_title(ui: &mut Ui, title: &str, subtitle: &str) {
    ui.add_space(2.0);
    ui.label(RichText::new(title).size(19.0).strong());
    ui.add_space(2.0);
    ui.label(RichText::new(subtitle).small().color(COLOR_TEXT));
    ui.add_space(4.0);
    ui.separator();
    ui.add_space(6.0);
}

pub fn card_frame() -> Frame {
    Frame::none()
        .fill(COLOR_CARD_BG)
        .stroke(egui::Stroke::new(1.0, COLOR_BORDER))
        .inner_margin(egui::Margin::same(14.0))
}

pub fn card(ui: &mut Ui, title: &str, add_contents: impl FnOnce(&mut Ui)) {
    card_frame().show(ui, |ui| {
        ui.label(
            RichText::new(title.to_ascii_uppercase())
                .size(13.0)
                .strong()
                .color(COLOR_ACCENT),
        );
        ui.add_space(8.0);
        add_contents(ui);
    });
    ui.add_space(8.0);
}

pub fn small_button(ui: &mut Ui, text: &str) -> egui::Response {
    let width = (text.chars().count() as f32 * 7.2 + 26.0).clamp(108.0, 240.0);
    ui.add_sized([width, 30.0], egui::Button::new(text.to_ascii_uppercase()))
}

pub fn primary_button(ui: &mut Ui, text: &str) -> egui::Response {
    ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = COLOR_BLUE;
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, COLOR_BLUE);
        visuals.widgets.hovered.bg_fill = Color32::from_rgb(24, 116, 184);
        visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, COLOR_ACCENT);
        visuals.widgets.active.bg_fill = Color32::from_rgb(12, 78, 132);
        ui.add_sized(
            [164.0, 34.0],
            egui::Button::new(RichText::new(text.to_ascii_uppercase()).strong()),
        )
    })
    .inner
}

pub fn success_button(ui: &mut Ui, text: &str) -> egui::Response {
    ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = COLOR_GREEN;
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, COLOR_GREEN);
        visuals.widgets.hovered.bg_fill = Color32::from_rgb(0, 190, 0);
        visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, COLOR_ACCENT);
        visuals.widgets.active.bg_fill = Color32::from_rgb(0, 128, 0);
        ui.add_sized(
            [164.0, 34.0],
            egui::Button::new(RichText::new(text.to_ascii_uppercase()).strong()),
        )
    })
    .inner
}

pub fn danger_button(ui: &mut Ui, text: &str) -> egui::Response {
    ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = COLOR_RED;
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, COLOR_RED);
        visuals.widgets.hovered.bg_fill = Color32::from_rgb(186, 36, 36);
        visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, COLOR_ACCENT);
        visuals.widgets.active.bg_fill = Color32::from_rgb(128, 24, 24);
        ui.add_sized(
            [102.0, 30.0],
            egui::Button::new(RichText::new(text.to_ascii_uppercase()).strong()),
        )
    })
    .inner
}
