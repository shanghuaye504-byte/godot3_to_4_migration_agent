# body by KoBeWi

EDIT: Scroll a bit further for interesting stuff.

This is meant to close https://github.com/godotengine/godot-proposals/issues/514

~~Note that THIS IS HEAVILY WIP. The implementation is incredibly hacked together for now, full of dead and commented out code. Also it's mostly unfinished. I wanted to open the PR early to make sure that this is going in the right direction.~~

In its current state you can do this:
```
var tween := get_tree().create_tween()
tween.tween_property($icon, "position", Vector2(340, 100), 4)
tween.tween_property($icon, "modulate", Color.red, 1)
```
which will result in
![kaJpR0TdMP](https://user-images.githubusercontent.com/2223172/92312770-4a748480-efc4-11ea-887a-2f90439aa1db.gif)

So onto details:
Tweens are no longer nodes. They are References, with very similar logic to SceneTreeTimers, designed in a "fire and forget" manner. You create a Tween with `get_tree().create_tween()`, which will result an empty Tween. To do something with it, you then call one of the tweening methods. These are:
`tween_property` - tweens a property between given values (equivalent of current interpolate property)
`tween_interval` - waits for given time (equivalent of a timer)
`tween_callback` - calls a method on an object (equivalent of current interpolate callback)
`tween_method` - calls a method on an object with a tweening argument that goes from initial to final value (equivalent of current interpolate method)

You can call as many tweening methods on the Tween as you want, they will be sequenced one after another, i.e. there's support for chaining out of the box. Parallel tweening will be done explicitly with a dedicated method.

As for the implementation, there two main classes: **Tween** and **Tweener**. Tween is basically a collection of Tweeners. When you call tweening method, it actually creates a Tweener. Tweeners are packed in a List. Tween will go through the list and process every Tweener and when it finishes, it goes onto another step in the sequence. The Lists of Tweeners for each step are contained in a Vector.

Internally, SceneTree calls `_step()` on all active Tweens. Each Tween then calls `_step()` on each current Tweener. `_step()` has a return value. When a Tweener returns `false`, it's considered finished (but doesn't get freed, in case you want to loop the Tween). If Tween returns `false`, it's removed from the list of tweens in SceneTree (and freed if you don't keep a reference). Tweener is also removed when the targeted object gets removed (whether this should happen silently or needs to be handled manually by user is up to discussion).

These are the basics. The new Tweens are going to work mostly like in the proposal (see the TweenSequence class linked in there). I yeeted the old Tween code, save for the interpolation (the `_interpolate` method in PropertyTweener, which is going to get cleaned up). The `_calculate_interpolation` method defined in `easing_equations.cpp` will stay there and since I need it in another class, there's a chance to expose it (I remember there was a request for it).

The thing that I'm the most unsure of is whether Tweens should be handled directly by SceneTree. But I don't have other idea how they could be handled, aside from maybe TweenServer.

-----

EDIT:
Ok, the feature implementation is complete. What's left is error handling and documentation.

Here's a brief summary of the features:
(scroll below for actual usage examples)

**Tween**
- Tweens are now Reference type handled by SceneTree, which makes them super cheap. They are intended for fire-and-forget use
- You create a Tween by using `get_tree().create_tween()` or `create_tween()` inside Node (the latter will automatically bind the Tween, see below)
- You can also use `get_tree().get_processed_tweens()` to get the list of all existing Tweens
- Tweens have process mode and pause mode, so they can process either in idle frame or physics frame and can be paused
- Tweens can also be bound to a Node, by using `bind_node(node)`. The Tween will not process if the node is not inside tree and will be automatically removed when the node is freed
- You can loop the Tween with `set_loops(loops)` and 0 will make infinite loop
- You can stop (reset), pause, resume and kill a Tween
- To actually Tween something, you need to use a tweening method (see below), which will return a Tweener
- You can call as many tweening methods as you want and they will be executed in a sequence
- If you want tweening method to run parallely, you can use `tween.parallel()`
- Using `Tween.set_parallel(true)` will make all subsequent Tweeners parallel
- You can also use `Tween.set_ease()` or `Tween.set_trans()` to set default easing and transition for a Tween
- Alternatively, there's a method `tween.interpolate_value(initial_value, delta_value, time, duration, transition, easing)` which allows you to manually interpolate a value with easing (supersedes #36997)

There are 4 available Tweeners:
**PropertyTweener**
- Created with `tween.tween_property(object, property, final_value, duration)`
- By default, PropertyTweener starts from current value at the time it starts tweening
- You can use `from()` to set a custom starting value
- You can also use `from_current()` to assign it the value it has currently (i.e. when creating the Tween)
- And finally, you can use `as_relative()` to make the final value be a relative value (so e.g. tweening position to Vector(100, 0) relatively will move it by 100 pixels instead of moving it to position (100, 0))
- PropertyTweener inherits transition and ease types from the Tween. You can set them with `set_ease(ease)` or `set_trans(trans)`
- You can also make the PropertyTweener delayed with `set_delay(delay)`

**IntervalTweener**
- Created with `tween.tween_interval(duration)`
- It just does nothing for given time, bruh

**CallbackTweener**
- Created with `tween.tween_callback(callback)`, where `callback` is a Callable
- Calls the given method
- To bind additional arguments to the method you can use `Callable.bind(args)`
- You can use `set_delay(delay)` to have a delay before the callback

**MethodTweener**
- Created with `tween.tween_method(callback, from, to, duration)`
- This is like PropertyTweener, but instead of tweening an actual property, it tweens an internal variable and calls a method with this variable
- To bind additional arguments to the method you can use `Callable.bind(args)`
- You can set easing type and transition type like in PropertyTweener
- You can also delay it
- This is super cool to use with lambdas

Ok, so these are features. Now on the actual usage, it basically boils down to:
```
var tween = get_tree.create_tween()
tween.tween_something(something args)
tween.tween_something(different args).some_settings_etc()
```
which will execute the sequence of 2 given tweening operations.

Some samples:
```
var tween = get_tree().create_tween()
tween.tween_property($Sprite, "position", Vector2(300, 100), 1).set_trans(Tween.TRANS_SINE)
tween.tween_property($Sprite, "modulate:b", 0, 1)
```
![ezgif-2-634b3229f1bb](https://user-images.githubusercontent.com/2223172/92388562-c6cbac80-f117-11ea-8f80-569596a6b8a7.gif)
```
var tween = get_tree().create_tween().set_trans(Tween.TRANS_ELASTIC).set_ease(Tween.EASE_OUT)
tween.tween_property($Sprite, "rotation", PI/2, 1)
tween.parallel().tween_property($Sprite, "position", Vector2(200, 200), 1).as_relative()
tween.tween_property($Sprite, "modulate", Color.red, 1)
```
![5GLRBjILLh](https://user-images.githubusercontent.com/2223172/92388353-72c0c800-f117-11ea-97ba-f2231a4e9136.gif)
```
var sprite = $Sprite
var tween = get_tree().create_tween().bind_node(sprite)
tween.tween_property(sprite, "position", Vector2(500, 0), 3).as_relative()
	
await get_tree().create_timer(1).timeout
remove_child(sprite)
await get_tree().create_timer(1).timeout
add_child(sprite)
```
![ezgif-2-2365f3574e52](https://user-images.githubusercontent.com/2223172/92388949-64bf7700-f118-11ea-9a4f-1171f9293a3e.gif)
Same as above but without bind
![ezgif-2-fc313369f2bb](https://user-images.githubusercontent.com/2223172/92388874-45c0e500-f118-11ea-9449-225d5278de19.gif)
```
var tween = get_tree().create_tween().set_loops(2)
tween.tween_property($Sprite, "position", Vector2(200, 0), 0.5).as_relative()
tween.tween_interval(0.5)
```
![ezgif-2-7e2e6499c732](https://user-images.githubusercontent.com/2223172/92389141-d1d30c80-f118-11ea-9119-525466cb1c55.gif)
```
var tween = get_tree().create_tween().set_loops() #-1 by default
tween.tween_interval(1)
tween.tween_callback($Sprite.hide)
tween.tween_interval(1)
tween.tween_callback($Sprite.show)
```
![ezgif-2-b3bc92085efb](https://user-images.githubusercontent.com/2223172/92389351-33937680-f119-11ea-8ec5-7cfa0958abfc.gif)
```
func _ready():
	var tween = get_tree().create_tween()
	tween.tween_method(set_label_text, 0, 10, 1)

func set_label_text(value: int):
	$Label.text = "Counting " + str(value)
```
![ezgif-2-64907598dcf6](https://user-images.githubusercontent.com/2223172/92389555-9be25800-f119-11ea-819a-1d39795c274e.gif)
Lambda version of the above:
```
var tween = get_tree().create_tween()
var label = $Label
tween.tween_method(func(value: int): label.text = "Counting " + str(value), 0, 10, 1)
```

If you have any questions or feature requests be sure to write them in the comments.

## comment by Xrayez

Nice to see it works out, see my previous comments revolving around this kind of interface in https://github.com/godotengine/godot/issues/26529#issuecomment-564798612 supporting this on the high-level.

## comment by KoBeWi

@Xrayez If you mean autostarting and handling pause, then it's already planned.
btw the code sample you given there will probably look like this:
```
var tween = get_tree().create_tween()
tween.tween_property($Godot, "modulate:a", 0, 5)
tween.tween_callback($Godot.queue_free) #alternative to connecting finished signal
```

## comment by dalexeev

> Parallel tweening will be done explicitly with a dedicated method.

Maybe something like this:

```gdscript
var tween := get_tree().create_tween()

tween.tween_property($icon, "position", Vector2(340, 100), 4)

tween.group_begin()
tween.tween_property($icon, "modulate", Color.red, 1)
tween.tween_property($icon, "scale", Vector2(2, 2), 1)
tween.group_end()
```

## comment by KoBeWi

> Maybe something like this:

Nah, it will be simpler. It's not mentioned in the OP, but the Tweens will make heavy use of chaining (every Tween/Tweener method returns that Tween/Tweener to allow multiple calls).

That said, your code will look like this:
```
var tween := get_tree().create_tween()

tween.tween_property($icon, "position", Vector2(340, 100), 4)

tween.tween_property($icon, "modulate", Color.red, 1)
tween.join().tween_property($icon, "scale", Vector2(2, 2), 1)
```
Parallel Tweening is going to be achieved with `parallel()` and `join()` methods followed by a Tweener method. The difference between the two is that `join()` will result in an error if there was no previous tweening command.

## comment by dalexeev

We must try to make this not only simple, but also as versatile as possible. How to get the following using your way:

![](https://user-images.githubusercontent.com/47700418/92325696-4c3a5880-f055-11ea-911d-90992b125e9b.png)

I had a thought about `await`:

```
await tween.tween_property( 1 )

tween.tween_property( 3 )
await tween.tween_property( 2 )

tween.tween_property( 4 )
await tween.tween_property( 5 )

tween.tween_property( 6 )
```

But this is too GDScript specific.

## comment by KoBeWi

> How to get the following using your way:

By using two Tweens. You'd need to add CallbackTweener 5b with a delay equal to duration of 5, which would create a new Tween that does 6. Tweens are cheap in the new implementation, so you don't have to worry about creating many of them.

Allowing asynchronous steps would make the implementation much more complicated. Although maybe I could add at least a `finished` signal for Tweeners to make your `await` code possible.

## comment by dalexeev

I got it. Something like this:

```
tween1.tween_property( 1 )
tween1.tween_property( 2 )
tween1.tween_property( 5 )
tween1.tween_property( 6 )

tween2.tween_interval( ... )
tween2.tween_property( 3 )
tween2.tween_interval( ... )
tween2.tween_property( 4 )
```

That is, you can always do without `.join()` if you add another `Tween`. But that's a little unintuitive.

## comment by KoBeWi

Ok, I completed the features. Check the added section in the OP.

## comment by kleonc

> var tween = get_tree().create_tween().set_loops(2)
> tween.tween_property($Sprite, "position", Vector2(200, 0), 0.5).as_relative()
> tween.tween_interval(0.5)
![gifExampleLoops](https://user-images.githubusercontent.com/2223172/92389141-d1d30c80-f118-11ea-9119-525466cb1c55.gif)

I don't think `set_loops(n)` should make tween execute `n + 1` times. I find it unintuitive.

## comment by KoBeWi

> I don't think set_loops(n) should make tween execute n + 1 times. I find it unintuitive.

`set_loop(n)` means "loop n times". Maybe it should be called `repeat`?

## comment by reduz

While I agree tween should be a reference, I think it should be something created in Node, not in SceneTree (even though it is processed in SceneTree), so you simply use it like

```
tween("property",values)
# or
$node.tween("property",values)
```

I would do the same change for timers

## comment by dominiks

Hi I just saw your rewrite on Twitter and I very much agree with the 'fire and forget' idea of tweens and many of the other changes and improvements you have made. In the past I found myself always creating tween objects on demand and never really figured out how to properly restart or reuse them.

### Creating tweens

Is there a specific reason that the ``create_tween`` function must be on the ``SceneTree``? I have the feeling it should be a function of ``Node`` with the tweens automatically binding to that node that "owns" them. Just throwing them at the tree without an "owner" probably works in 99% of the cases but it might be a source of confusing bugs where tweens run through pause or show unexpected behavour differing from the "owner" node because I forgot to bind the tween after creation. I would probably just bind them always to prevent this.

Also it fits a bit better into the composition philosophy of Godot when the tween is created on the current ``Node`` instead of the tree which feels a bit more global.

### Auto start tweens

If I understand correctly tweens automatically start on the next frame after their creation? And if you want to delay the start you would add a delay with ``set_delay`` or inserting an interval tween in the front? I cannot remember if I ever actually wanted to not start a tween immediately after creation but preventing the auto start to start them manually at an arbitrary point could be useful in some scenarios?

### Parallel tweens

Just creating multiple tweens to run at the same time will probably enough in most cases but you are right that there needs to be some sort of ``join`` mechanism for more complex tweening. Calling this process ``join`` is a good fit as the terminology and thought process behind this is similar to multithreading. Intuitively I would expect it to work something like this:

```
var tween := create_tween()
tween.tween_property(...) #A

var parallel := tween.join()
parallel.tween_property(...) # B
parallel.tween_property(...) # C

tween.tween_property(...) # D
```


This should run tween A, then B and C parallel and after that tween D. This underlines the idea that calling the ``tween_*`` functions on the tween chains them one after the other and a group of parallel tweens is just chained in.

I think the names of the ``tween_*`` functions could be changed into something that underlines that they are added instead of overwritten (it is possible to think a created tween can only run one tween function) and that they run in sequence. But I don't have a good name for that at the moment. Something like ``add_interpolate`` hints that multiple tweens are possible but does not indicate that they are a sequence.

## comment by eon-s

I don't like it accessed via SceneTree, it makes the tween access a bit dirty, while it can use a Node like it is currently and expose configuration via inspector which would be great for many workflows and more godot-like.

## comment by API-Beast

Usually you would combine tweens with one or multiple AnimationPlayer to get most of the functionality in this pull request. I think it is overdoing it a little, trying to do too much with tweens alone.

Edit: the relative movement and the fixed amount of loops is something I would like to see in the AnimationPlayer instead.

## comment by MagellanicGames

The idea seems solid and very much an improvement, removing it from being a node and only accessible through the SceneTree just seems a bit....off.  It's probably just me.  I certainly like occasionally using "get_tree().create_timer" in an in-line way for yields but I will often pull that back into a node composed within a scene so it's a bit cleaner and self-contained.  I know it's handled now, so that in case a yield returns to a now dead node/scene it wont crash but this would have to be handled as well with tweens.  
I'm well aware though that this could just be me, but I thought I would voice the concern in case what I'm talking about has any relevance.

## comment by sketchyfun

Maybe it's just me, but I feel like the default behaviour of a tween should be to process in parallel, which is how it works currently. The join() function doesn't really make sense in terms of doing things in parallel. I'd probably do something like:

parallel:
tween.interpolate_property(blah)
tween.interpolate_property(other_blah)
tween.start()

sequence:
tween.interpolate_property(blah)
tween.chain().interpolate_property(other_blah)
tween.start()

(not sure if tween.start() is still a thing in this PR?)

Not sure if 'chain' is the best word (maybe append?), but I think something like that would better describe the idea of creating/adding to a sequence rather than 'join'

## comment by KoBeWi

> I have the feeling it should be a function of Node with the tweens automatically binding to that node that "owns" them.

I actually had this idea already. Seeing how some people requested it I'll add it as an alternative way of creating Tweens.

> Auto start tweens [...]

If you don't want the Tween to start immediately, you can call `stop()` or `pause()` after it is created. This will be mentioned in the docs.

> This should run tween A, then B and C parallel and after that tween D. This underlines the idea that calling the tween_* functions on the tween chains them one after the other and a group of parallel tweens is just chained in.

This can be already achieved with
```
var tween = get_tree().create_tween()
tween.tween_property(...) #A
tween.tween_property(...) # B
tween.join().tween_property(...) # C
tween.tween_property(...) # D
```
When you use `join()` or `parallel()` method, any tweening method called immediately after will run in parallel with the previous one. Tween will go to next step only when all parallel Tweeners have finished.

> I think the names of the tween_* functions could be changed into something

In my prototype they were called `append_*`. I could rename this probably.

> Usually you would combine tweens with one or multiple AnimationPlayer to get most of the functionality in this pull request. I think it is overdoing it a little, trying to do too much with tweens alone.

Long before the PR I made a prototype in GDScipt and have been using it in my project for few months. Tweens made this way are fun to abuse for lots of different things. I never needed to combine them with AnimationPlayer, this is only useful when you want to visually design some animation.

> I know it's handled now, so that in case a yield returns to a now dead node/scene it wont crash but this would have to be handled as well with tweens.

This is irrelevant. You don't need to use yield/away with Tweens, you just tell them to animate something and they animate it. If the animated object is removed midway, the Tween will automatically stop and get deleted.

> Maybe it's just me, but I feel like the default behaviour of a tween should be to process in parallel, which is how it works currently.

Dunno, Tween chaining was requested for ages. Personally I more often tween something sequentially than parallely. Maybe I could add a method that makes paralleling default? 🤔

## comment by kleonc

> `set_loop(n)` means "loop n times". Maybe it should be called `repeat`?

The main problem here is behaviour, not naming. I think the most common use case will be to make tween execute exactly `n` times in total and having to call `set_loop(n - 1)` (or however this method will be named) will be counterintuitive and simply annoying. It will be counterintuitive because in most programming languages when you want to execute some code exactly `n` times you use loop (like `for`) where you provide template (code block) and tell how many times it should be executed. In your current tween interface you're providing a template (tween) which will be executed once and you can additionally tell how many more times it should be executed. I think it's not what programmers are used to and a common sense is to change it. Of course it's just my opinion and I might be wrong.
So I suggest changing behaviour to `set_loop(total_number_of_iterations/executions)` (however this method will be named).

For current behaviour: yes, `repeat` is better name (but it still could be misunderstood because of analogy to standard loops).

## comment by MarcusElg

> > `set_loop(n)` means "loop n times". Maybe it should be called `repeat`?
> 
> The main problem here is behaviour, not naming. I think the most common use case will be to make tween execute exactly `n` times in total and having to call `set_loop(n - 1)` (or however this method will be named) will be counterintuitive and simply annoying. It will be counterintuitive because in most programming languages when you want to execute some code exactly `n` times you use loop (like `for`) where you provide template (code block) and tell how many times it should be executed. In your current tween interface you're providing a template (tween) which will be executed once and you can additionally tell how many more times it should be executed. I think it's not what programmers are used to and a common sense is to change it. Of course it's just my opinion and I might be wrong.
> So I suggest changing behaviour to `set_loop(total_number_of_iterations/executions)` (however this method will be named).
> 
> For current behaviour: yes, `repeat` is better name (but it still could be misunderstood because of analogy to standard loops).

Totally agree. Iterating n + 1 times is just confusing, makes it feel like a do loop. I feel like most poeple exspect it to iterate n times and will have to go back and change their code.

## comment by dominiks

I definitely support that chaining should be the default instead of parallel running but a good compromise would be to have two seperate functions to create the tween object: one creates a chaining one and the other creates one that runs all tweens at the same time.

> If you don't want the Tween to start immediately, you can call stop() or pause() after it is created. This will be mentioned in the docs.

Fair enough then. If the documentation covers this all is well.

> This can be already achieved with

```
var tween = get_tree().create_tween()
tween.tween_property(...) #A
tween.tween_property(...) # B
tween.join().tween_property(...) # C
tween.tween_property(...) # D
```

> When you use join() or parallel() method, any tweening method called immediately after will run in parallel with the previous one. Tween will go to next step only when all parallel Tweeners have finished.

I don't know but something about doing it this way feels odd to me, maybe the empty ``join`` function that looks a bit out of place or useless. It might be just me but it would be good if the simultaneous execution of tweens B and C is not created by adding only tween C in a special way. Adding some empty lines for formatting obviously helps make B and C look like they belong together. Creating "tween-group" objects as I suggested makes it a bit easier  (for me) to conceptualize the sequence and parallel relations.



## comment by KoBeWi

After some feedback, I added a `create_tween()` method in Node, which will create a Tween and automatically bind it to that node. Also Tween got a new `append()` method, which takes a Tweener. Node got an alternative `tween_property` method that returns PropertyTweener created for that object. With all this combined, you can now do:
```
create_tween().append(tween_property("position", Vector2(100, 100), 1)).append(tween_property("position", Vector2(100, 200), 1))
```
This actually gives lots of possibilities for creating custom Tween-convenience methods. But creating Tweeners manually is not exposed to GDScript (right now).

Consequently, `tween_*` methods in Tween were renamed to `append_*` to make it more obvious that the Tweener created this way is automatically appended to Tween.

From other changes, I added a pause mode called TWEEN_PAUSE_BOUND, which makes the Tween pause when the bound node is paused (without bound node it works like TWEEN_PAUSE_STOP).

I haven't touched `set_loops` and `parallel` yet. I'm not sure what to do with the latter. Maybe I should add a `set_parallel()` method which makes Tween parallel by default and then `chain()` method which chains the Tweeners when Tween is in parallel mode? (also `parallel()` would be removed as `join()` is enough, but it wouldn't have the error which is rather useless).

I yet have to update the OP.

## comment by avedar

The ability to use custom curves for both the ease and trans would be greatly appreciated

## comment by pixelpicosean

It's great to have nodes ability to create local tweens, [very similar API](https://github.com/pixelpicosean/voltar/tree/develop/src/engine/tween) to my JavaScript port of Godot ;) I did the same thing for performance, but have made `Tween` a completely self contained class that developer can add to any node when they want (a little bit hard to use because you need to update the manager yourself, but anyway as far as I know I am the only developer using that engine).

## comment by Ansraer

> Consequently, tween_* methods in Tween were renamed to append_* to make it more obvious that the Tweener created this way is automatically appended to Tween.

Not sure if I am a fan of this. If I understand this correctly I would have to use create_tween().append_property(...) to tween a property. My problem with this is that "append property" doesn't make it obvious for people who haven't read the docs that the appended property is being tweened. (Is tweened a word?)

In contrast I immediately understood your create_tween().tween_properties(...) examples even without reading your explanation.
tbh I would prefer it if this change was reverted.

I am also not a huge fan of parallel() and join(). Based on my understanding of the earlier comments the two of them both run the next command in the chain concurrently with the previous command(s).
Being used to a fork/join workflow this confused me a LOT.
I would recommend parallel() = run the next tween concurrently, fork() telling the tweener to make parallel the default mode and join() being used to switch back to sequential mode.

(Edit: minor spelling correction, I typing am on my phone)

## comment by pixelpicosean

> The ability to use custom curves for both the ease and trans would be greatly appreciated

I also vote for custom curve support, but we may not need Godot's built in `Curve` because it may be better to use a `Tween` node with `Curve` and using the editor to do the editing. My suggestion is something like *power* based curves that may use a cubic spline for implementation, so developers can use cubic params to define the easing. 

## comment by KoBeWi

Ok, I think the code is mostly finished.

From recent changes:
- `set_loops(n)` will make the Tween execute n times instead of n + 1
- I added `set_parallel(true/false)` which will make the Tween parallel by default if set to true (true is also default argument here)
- `join()` was removed. I originally added it, because DOTween calls this method join, but the name is rather confusing, so bye
- added `chain()` method, which makes one Tween operation sequenced when `set_parallel()` is true
- Tweens created outside SceneTree (i.e. with `Tween.new()`) and Tweens that have finished and got removed are now invalid
- You can use invalid Tweens for manual interpolation via `interpolate_value()`, but attempting to append a Tweener will result in an error
- Tweeners got a proper error message that points to correct usage when created manually (e.g. `PropertyTweener.new()`)

Things to consider:
- `parallel()` might need a new name, because it's too similar to `set_paralell()`. Or at least I imagine some people would say so.
- maybe renaming the `append_*` methods yet again as suggested in https://github.com/godotengine/godot/pull/41794#issuecomment-688609551. Not sure what would be a better name

I can now move to writing documentation and the PR will be finished.

> The ability to use custom curves for both the ease and trans would be greatly appreciated

This is a thing for another time. There are plans to rewrite existing interpolaters, see #22513

## comment by djrain


After considering this for a while, I have to propose the opposite of the current implementation: you simply instruct the tween to wait and finish the last tween before proceeding, or not:

tween.tween_property(...).wait() #A
tween.tween_property(...) #B
tween.tween_property(...) #C
tween.wait()
tween.tween_property(...) #D
...

There may be a better name than "wait" (wait_to_finish? kinda long, but totally clear, and we have autocomplete)
But I see this as having the following advantages over the current join/parallel method:

- Superior readability. With the special call more visible at the end of the line, it's easier to see which sections are to run parallel. Sure, you could move parallel() to the end of the previous tween, but it makes a lot more sense to have that come immediately before what you're running in parallel, so I don't see that as an equally good option.

- Does not needlessly change the current behavior of parallel = default. I'm all for changing behavior when it's justified, but I don't see a clear majority in favor in this case. Actually, I argue that having parallel as default is...

- Way more intuitive. If my boss tells me to do x, y and z, I assume he means to do them in no particular order, in parallel if possible. Sequentiality is what requires explicit instruction: "Do x, THEN when you are finished, do y". You'd never tell someone "don't wait until you do the next task". It's kinda like a confusing double negative, it's just not natural.


## comment by KoBeWi

Ok, finally finished this. The PR probably needs some testing (because I didn't test much yet).

@djrain I haven't mentioned it, but the `parallel()` call doesn't need to be followed immediately. Code like
```
var tween = create_tween()
tween.append_property(...)
tween.parallel()
tween.append_property(...)
```
will still work perfectly. For opposite behavior, you can use
```
var tween = create_tween().set_parallel()
tween.append_property(...)
tween.chain()
tween.append_property(...)
```
Tweens are sequential by default, because it's more often useful from my experience. Maybe eventually we could introduce global tweening options, like default paralleling, trans/ease types etc. but IMO having to add `set_parallel()` in case you want fully parallel tween is not that bad.

## comment by sketchyfun

Is it possible to chain parallel tweens? i.e:

var tween = create_tween()
tween.parallel()
tween.append_property(...) # simultaneous 
tween.append_property(...) # simultaneous 
tween.chain()
tween.append_property(...) # this one happens after

## comment by KoBeWi

 > Is it possible to chain parallel tweens? i.e:
var tween = create_tween()
tween.parallel()
tween.append_property(...) # simultaneous
tween.append_property(...) # simultaneous
tween.chain()
tween.append_property(...) # this one happens after

That's what `set_parallel()` is for. `parallel()`/`chain()` affect only the subsequent operation. You can do `tween.set_parallel(true)` (true is optional) to make all following operations parallel and then `set_parallel(false)` to make it sequential again.

In case of your snipped, you just have to change `parallel()` to `set_parallel()`.

## comment by sketchyfun

Ahh I understand now, good stuff :)

## comment by Ansraer

Looked through your PR, looks very good so far. Definitely an improvement when compared to what we currently have.

I am however not certain if I like how tweens are hardcode into scene_tree directly, imo there should be a modular layer between them. To be honest I am not familiar enough with godots internals to suggest a better solution, just feel like there should be a "SceneTreeExtensionsManager" or something like that between the scene_tree, an integral part of Godot, and tweens, which are, in comparison, not all that important.
Maybe someone more qualified could weigh in on this?

My other major problem are the renamed append_* methods. Does obj.append_property() create a new property and add it to some list? Does obj.append_method() append code to some method or append a method call to something?
I really preferred the initial tween_* names. That name made it perfectly clear that they were tweening a property/method call...
Not sure if anyone else agrees with me, but this is currently my biggest problem with this PR.


## comment by MarcusElg

> Looked through your PR, looks very good so far. Definitely an improvement when compared to what we currently have.
> 
> I am however not certain if I like how tweens are hardcode into scene_tree directly, imo there should be a modular layer between them. To be honest I am not familiar enough with godots internals to suggest a better solution, just feel like there should be a "SceneTreeExtensionsManager" or something like that between the scene_tree, an integral part of Godot, and tweens, which are, in comparison, not all that important.
> Maybe someone more qualified could weigh in on this?
> 
> My other major problem are the renamed append_* methods. Does obj.append_property() create a new property and add it to some list? Does obj.append_method() append code to some method or append a method call to something?
> I really preferred the initial tween_* names. That name made it perfectly clear that they were tweening a property/method call...
> Not sure if anyone else agrees with me, but this is currently my biggest problem with this PR.

I agree with the names, the original tween names where better but some people dissagree. Maybe it would be best to create a poll to see what the majority would prefer.

## comment by KoBeWi

tbh I also preferred the old names. I added a commit that reverts the rename and in another commit I removed the `append` method and `Node.tween_property`. It makes little sense to have single method that works differently. `append` could be interesting to use with something like CustomTweener, which can be coded by script, but the current Tweeners provide everything needed anyways. It's also easier to add something than remove it. In worst case, we can still do a small breakage before 4.0 stable is released.

## comment by samdze

> We must try to make this not only simple, but also as versatile as possible. How to get the following using your way:
> 
> ![](https://user-images.githubusercontent.com/47700418/92325696-4c3a5880-f055-11ea-911d-90992b125e9b.png)

I'd like to be able to create something like this with a single tween. All the other major tweening libraries let you do this.
```
var tween := create_tween()
tween.tween_property(...) # 1

var first_parallel := tween.parallel()
first_parallel.tween_property(...) # 2
first_parallel.tween_property(...) # 3

var second_parallel := tween.parallel()
second_parallel.tween_property(...) # 4

var inner_sequence = second_parallel.sequence()
inner_sequence.tween_property(...) # 5
inner_sequence.tween_property(...) # 6

tween.tween_property(...) # This runs after everything else is done.
```
This is now a self-contained animation that doesn't need to spawn other tweens and is way more flexible.
This comes with the cost of being a bit more complex to write, but only very complex behaviours are going to be like this, leaving the rest simple enough.

## comment by Kinwailo

How about all `tween_*` function return new reference hold the new start time.
```
var tween := create_tween()

# run in sequence
tween = tween.tween_property(...)
tween = tween.tween_property(...)
or
tween.tween_property(...).tween_property(...)

# run in parallel
tween.tween_property(...)
tween.tween_property(...)

# mix
var t1 := tween.tween_property(...)
var t2 := tween.tween_property(...)
tween.tween_property(...)
var t3 := tween.wait(t1) or tween.wait_all(t1, t2) or tween.wait_any(t1, t2)
t3.tween_property(...)
```


## comment by samdze

@Kinwailo Seems like a good idea.
Would be perfect if returned references could support some sort of comparisons to know which one ends first/last, and if functions like max(twens...) and min(tweens...) could be provided as a quality of life.
I'm a little concerned about the effective sequentiality of tweens concatenated this way, there may be a few corner cases in which a tween intended to play after another bunch of tweens starts playing when one of them is still in its last frame.

Oh, aside that, I'd very like the ability to:
- Manually update a tween, something like:
`tween.update(delta)`
to fast forward the tween by an arbitrary amount of time.
- Have a tween in a mode in which only manual updates make it work.

## comment by Ansraer

@Kinwailo Sorry, but I don't see what the advantage of your suggestion would be. It is possible to do the same thing with the current implementation just by using set_parallel().
Plus, changing the returned object in such a way would probably break quite a few assumptions that developer experienced with method chaining might have.

@samdz I like your update suggestion, though I would probably call it set_delta(delta) instead.

Assuming we get a set_delta method it should be possible to only allow manual updates by simply pausing the tween.

## comment by KoBeWi

 > I like your update suggestion, though I would probably call it set_delta(delta) instead.
Assuming we get a set_delta method it should be possible to only allow manual updates by simply pausing the tween.

This is a matter of exposing the `step(delta)` method to GDScript and modifying it to allow manual stepping of paused Tweens. Name `set_delta` suggests something completely different.

Alternatively, this is already possible by using `pause()`, `play()` and `set_time_scale()` in a clever way 🙃

EDIT:
Added, the method is called `custom_step`. I was actually thinking about adding this method before, but decided to wait until someone actually requests it.

## comment by Ansraer

Well, step would only allow changing the progress based on the current state of the tween. A setter would make it possible to track the progress outside of the tween and would make it easier to jump around. Useful if you want to skip forward/backward to a specific part of the animation or if you want to reset the tween manually.

Based on his request I assumed he wanted to have a setter to directly control the current state of the tween. I can see use cases for both methods, would it be any trouble to also add a custom_set_time() method?

## comment by KoBeWi

> would it be any trouble to also add a custom_set_time() method?

The problem is that progressing the tween interpolates the new value. To set the time to an arbitrary point backwards, some reverse interpolation would be needed (not sure if simply interpolating with negative delta would work). Also the Tween would need to keep track of current time and total time (right now only Tweeners keep track of time). This would make the code more complicated overall.

For arbitrary seeking in an animation, you should either use the Animation resource or implement it yourself. This is not common enough use-case for Tweens to add it.

## comment by Ansraer

Oh, I assumed that tweens would store the starting values of all modified variables until the transition was done. Now that I am thinking about it I can see the problems this approach would have. Negative delta might work for some transition types but definitely not all.

Yeah, I can see how implementing and maintaining this would be more trouble than it is worth.

## comment by samdze

Uhm, I often rely on tweens having the ability to go backwards in other engines and I find it very very useful...

## comment by me2beats

is it still ok to leave suggestions here or is there a better place to do this?

`get_processed_tweens` — why not just `get_tweens`?

## comment by KoBeWi

> get_processed_tweens — why not just get_tweens?

Because there might exist Tweens outside SceneTree and they are not returned by this method. This name makes it more clear.

## comment by KoBeWi

Rebased with changes from #42683. `binds`/`params` were removed, you can now use `Callable.bind` (it's mentioned in the doc too). It was a bit sad to remove argument called `p_arams` xd

Unfortunately `Callable.bind` seems to be broken right now and returns null, so the changes are untested yet. Also not sure how to handle the additional arguments when printing error.

## comment by MarcusElg

Are there any planned features that haven't been implemented or will this be merged soon?

## comment by KoBeWi

The PR has a very good base of features and there's nothing planned anymore for now, but hard to say when will it be merged (someone needs to review it and it's big).

tl;dr no/no

## comment by KoBeWi

I just pushed another commit that changes how time is processed in Tweens. Previously (I mean in my PR), the steps were basically deferred. E.g. if there were two steps with duration of 0.01 and the delta was 0.016, the Tween was doing full 2 steps on span of 2 frames. Now it will do 1 full step and 0.006 seconds of second step. So the Tween will step Tweeners until the cumulative delta is exhausted.

To explain it better, here's a code to test:
```
var tween = create_tween().set_speed_scale(100)
tween.tween_property($Sprite, "modulate", Color.red, 0.01)
tween.tween_property($Sprite, "modulate", Color.red, 0.01)
tween.tween_property($Sprite, "modulate", Color.red, 0.01)
tween.tween_property($Sprite, "modulate", Color.red, 0.01)
tween.tween_property($Sprite, "modulate", Color.red, 0.01)
tween.tween_property($Sprite, "modulate", Color.blue, 0.01)
await get_tree().idle_frame
await get_tree().idle_frame
print($Sprite.modulate)
```
Before my last commit, this prints red color. Now it prints blue, because speed scale of 100 means a delta of 1,6 and all Tweeners are done in one frame, instead of 6 frames. This also means that CallbackTweeners with no delay are effectively parallel by default, because they execute all on the same frame.

EDIT:
Also rebased due to conflicts.

## comment by KoBeWi

Rebased and fixed some bugs (the GIFs in the OP are a nice test suite 🙃).

EDIT:
Also updated the OP with some more recent info/code. Not sure if it contains everything, read all comments if you want the full picture heh.

## comment by Byteron

I so want this. Hope it gets merged soon!

## comment by AnidemDex

I really like this. Hope the creator of [Anima](https://github.com/ceceppa/anima) take a look at this.

## comment by KoBeWi

I had to squash the commits to make rebasing easier. Technically it might be ready to merge 😏

## comment by akien-mga

Seems like you need to rebase to fix the `Reference` -> `RefCounted` change.

## comment by akien-mga

We discussed this in a PR review meeting today and decided that it should be good to merge and YOLO-test it in the `master` branch.

I'd like to see an amend of the commit message to add more details about what the rewrite actually changes in the body of the commit message.

## comment by KoBeWi

@akien-mga Done.

## comment by akien-mga

Thanks!

## comment by dreamsComeTrue

I would sell my family to see that in 3.x :stuck_out_tongue_closed_eyes: 

## comment by KoBeWi

3.x version was done long ago: https://github.com/godot-extended-libraries/godot-next/pull/50
It's worse, but I've been using it successfully in many projects.

## comment by dreamsComeTrue

> 3.x version was done long ago: [godot-extended-libraries/godot-next#50](https://github.com/godot-extended-libraries/godot-next/pull/50)

Eh, it's a shame it's non-native version though :disappointed: and lacks a lot of awesomeness from the PR.
I try to keep my project(s) as clean as possible and not mix-in other languages (I use mainly C#).
But thanks anyway! :) 

## comment by alexzheng

Would you please add a finished callback for a Tweener?

Something like
tween.tween_property($Sprite, "position", Vector2(200, 0), 0.5).on_ finished(callable)

This callback will be called after the move position animation finished.

## comment by KoBeWi

@alexzheng You can just do `tween_callback(callable)`, not sure why would you need a signal. Also, for feature requests, please open a proposal.

## comment by alexzheng

it would be much easier for parallel tweezers.
For example 
tween.parallel().tween_property($Sprite, "position", Vector2(200, 0), 0.5).on_ finished(callable)
tween.parallel().tween_property($Sprite2, "position", Vector2(200, 0), 1).on_ finished(callable2)


## comment by KoBeWi

I just checked and Tweeners do already have `finished` signal. So you can do
`tween.parallel().tween_property($Sprite, "position", Vector2(200, 0), 0.5).finished.connect(callable)`

## comment by DozyBird

Is it possible to find existing tweens bound to a particular node? 

If I understand right, the only method right now is iterating through all the results of `get_tree().get_processed_tweens()`.

## comment by KoBeWi

It's not possible right now. Also `get_processed_tweens()` returns *all* Tweens and you can't get the bound node from a Tween, so the best way to have a list of Tweens bound to a node is make one yourself (i.e. put any created Tween in an Array variable).

If you think Tweens should support that normally, open a proposal.

## comment by alexzheng

This Tweens implementation is much better than the 3.x. 
Would it be back ported to 3.x?

## comment by KoBeWi

@alexzheng There is a very similar implementation in GDScript that you can use in 3.x: https://github.com/godot-extended-libraries/godot-next/tree/master/addons/godot-next/references/tween_sequence
There are no plans to backport new Tweens, they'd have to be a separate class, because there is too much compatibility breakage.

## comment by alexzheng

This new tween may not required to be compatible with the Tween Node, It would be nice if it could be available as another option in 3.x,  just keep the Tween Node as it was, personally, I really do not like the Tween node.

## comment by alexzheng

@KoBeWi 
Check this code snippet
The position animation will jump to the final value and finished after scale animation finished.

var tween := get_tree().create_tween()
tween.tween_property($Icon, "position", Vector2(600, 900), 5.0).finished.connect(func() : printt("position finished"))	
tween.parallel().tween_property($Icon, "scale", Vector2(5, 5), 1.0).finished.connect(func() : printt("scale finished"))


## comment by KoBeWi

@alexzheng Open an issue about it.

## comment by seppoday

Hello @KoBeWi I don't know if it is a bug or not so I am posting this comment. I tried to queue_free() my node when there was tween in the scene looping. When I tried to do it whole game just crashed without errors or anything. Solution was to kill tween before freeing node. Maybe there is some way to auto free tween when someone free node?

Ps: Seems like creating tween under this node and not by get_tree() is also solution. When I did it I didnt need to call kill() anymore. So probably fault on my side. I will delete this comment soon. Leaving for now. Maybe in fact there is bug or not.


![Godot_v4 0-alpha1_win64_LGsagz5jgN](https://user-images.githubusercontent.com/62170071/151451150-1370753e-40ee-4ec2-b291-53a2b814e127.png)



## comment by KoBeWi

@seppoday The Tween should auto-kill when the object gets deleted, so it sounds like a bug. Open a new issue with some minimal project

## comment by owstetra

@KoBeWi 

> @seppoday The Tween should auto-kill when the object gets deleted, so it sounds like a bug. Open a new issue with some minimal project

i guess it's a bug, because when i use a tween in a button for a menu, then close and free that menu i get this warning :
```
W 0:00:09:0746   start: Target object freed before starting, aborting Tweener.
  <C++ Source>   scene/animation/tween.cpp:702 @ start()
```


## comment by KoBeWi

This is expected, if you free an object before animation starts, you get this warning. Although maybe it's not useful, idk 🤔

## comment by owstetra



> This is expected, if you free an object before animation starts, you get this warning. Although maybe it's not useful, idk thinking

But the animation is already started and finished, but for some reasons i still get this warning

```
var ButtonTween : Tween = get_tree().create_tween()
ButtonTween.set_pause_mode(Tween.TWEEN_PAUSE_PROCESS)
ButtonTween.tween_property($BackgroundFocus, "rect_size", Vector2(0, self.rect_size.y), 0.15).set_trans(Tween.TRANS_LINEAR)
```
This code i used it in a button when it's pressed for a Pause menu to animate the button, but if i change the level or go to the main menu or close the game i get the warning



## comment by KoBeWi

I tried your code and I don't get this warning. Can you share some minimal project? Also you could open a new issue.

## comment by girng

Just a bit of clarification (that maybe could be added somewhere?): What about tweens that are used over and over again, when the node doesn't get removed? I tested this, and the object count in the debugger continues to shoot up. Do those eventually get removed, or does the node need to be free'd?

## comment by KoBeWi

All Tweens are removed automatically when not used anymore, but there is a known issue when it doesn't work: #52699

## comment by PoisonousGame

Tween changes so much that the documentation is not yet sufficient to cover all use cases. I found a problem when using it that tween cannot be created outside the function, if this is not a bug, then it should be noted.


```gdscript
var tween
func _ready() -> void:
	tween = create_tween()

func transition()->void:
      tween.tween_property($Sprite, "modulate", Color.red, 1)
```


## comment by sketchyfun

> Tween changes so much that the documentation is not yet sufficient to cover all use cases. I found a problem when using it that tween cannot be created outside the function, if this is not a bug, then it should be noted.
> 
> ```gdscript
> var tween
> func _ready() -> void:
> 	tween = create_tween()
> 
> func transition()->void:
>       tween.tween_property($Sprite, "modulate", Color.red, 1)
> ```

Can confirm I had strange issues when using a tween created outside a function. The error wasn't exactly clear of what was going wrong, either

## comment by KoBeWi

The documentation has countless examples where Tween animation is defined right after its creation, discourages re-use and tells you that you should use `stop()` when doing it.

But maybe the error should tell that too.

## comment by TokisanGames

I am using tweens extensively in code. The key lines in the documentation are these:

```
Note: All Tweens will automatically start by default. To prevent a Tween from autostarting, you can call stop() immediately after it is created.

Note: Tweens are processing after all of nodes in the current frame, i.e. after Node._process() or Node._physics_process() (depending on TweenProcessMode).
```

That means you created an empty tween in ready, the tween begins that frame and continues looping indefinitely, then later on a subsequent frame, you're adding additional properties to change. The docs don't say what is supposed to happen when you add tweens while its running. Create it and set it up in the same frame you want it to run, or stop it upon creation for set up later as KoBeWi wrote.

## comment by PiewieP

How are Tweens supposed to be created when continuously tweening something in _process()? Or is that a bad use case for them?

## comment by TokisanGames

Generally, new devs should not create tweens in process. You don't want to create tweens 300 times per second. However, you can do it if you are manually checking the frequency and ensuring you're only creating them one every X seconds where X is less than or equal to your tween time. 