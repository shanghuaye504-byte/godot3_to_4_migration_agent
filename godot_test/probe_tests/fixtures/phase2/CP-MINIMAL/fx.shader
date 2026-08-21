shader_type canvas_item;

uniform vec4 tint : hint_color;

void fragment() {
	COLOR = tint;
}
