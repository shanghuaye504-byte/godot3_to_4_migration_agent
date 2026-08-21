shader_type canvas_item;

uniform sampler2D tex : hint_albedo;

void fragment() {
	COLOR = texture(tex, UV);
}
