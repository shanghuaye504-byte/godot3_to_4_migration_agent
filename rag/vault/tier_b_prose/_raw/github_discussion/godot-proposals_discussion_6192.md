# body by FeldrinH

In Godot 4.0 beta, the `onready` keyword has been turned into the `@onready` annotation. I feel like there is a case to be made that this is confusing and inconsistent.

The documentation for GDScript clearly states about the semantics of annotations ([reference](https://docs.godotengine.org/en/latest/tutorials/scripting/gdscript/gdscript_basics.html#annotations)):

> Annotations affect how the script is treated by external tools and usually don't change the behavior.  

In my opinion `@onready` violates both of these statements:
* Running something during node init or during `_ready` is a concern entirely internal to the node, so I would argue `@onready` does not affect how the script is treated by external tools.
* Running something during `_ready` instead of during node creation is a significant change to how the statement behaves, so I would argue that `@onready` does change behavior.

Given this, I propose changing `@onready` back into the `onready` keyword, like it was in Godot 3, as that would make it consistent with the stated distinction between annotations and keywords.

As an added bonus, this change would in my opinion improve readability, because `onready` is used a lot and I find having lots of `@` symbols makes the code harder to read beacause of the visual noise it creates.

## comment by dalexeev

I think this is more of a bug in the documentation. For example, `@export` annotations affect the result of `get_property_list()` and the behavior of `duplicate()` (exported variables will be copied when duplicating a node/resource, unlike other variables).

The `@rpc` annotation has a very big effect on behavior too.

## comment by dalexeev

We recently discussed the annotations vs keywords issue at a GDScript team meeting. While we have not been able to formalize a general rule about which option should be used for a new functionality, we have reached a consensus that existing keywords and annotations should not be affected. See:

* godotengine/godot-docs#9188
* [Engine development / Engine core and modules / Scripting development](https://docs.godotengine.org/en/latest/contributing/development/core_and_modules/scripting_development.html)

> The documentation for GDScript clearly states about the semantics of annotations ([reference](https://docs.godotengine.org/en/latest/tutorials/scripting/gdscript/gdscript_basics.html#annotations)):
> 
> > Annotations affect how the script is treated by external tools and usually don't change the behavior.

This confusing statement was also corrected in the user manual by the above PR. Annotation semantics are mentioned in the contributor documentation.

So I think all the questions raised here have been addressed. Thanks for your input!