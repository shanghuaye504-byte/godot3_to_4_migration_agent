# body by KoBeWi

This PR removes Fille/Directory from core bind and binds FileAccess/DirAccess instead.

The "new" classes have almost the same API as the old ones, but there are some changes. Most notable changes are `open()` being static and lack of `close()` method. I updated the docs to reflect that.

## comment by reduz

For the error, I think you could do something like
`thread_local Error last_file_open_error = OK` in the cpp
then set it when calling the static open() function, finally a 
`static Error FileAccess::_get_open_error();` that you bind to the script to get that error


## comment by KoBeWi

This `thread_local` thing is useful. I could also be used in the recently added JSON methods.

## comment by KoBeWi

I need some help with C#. I can't compile it locally and relying on CI to spot the errors is... well, bad xd
Could someone send me a fixed `BuildOutputView.cs` file? >_>

## comment by raulsntos

This should fix the C#:

```diff
diff --git a/modules/mono/editor/GodotTools/GodotTools/Build/BuildOutputView.cs b/modules/mono/editor/GodotTools/GodotTools/Build/BuildOutputView.cs
index c1f8d3f874..4d40724a83 100644
--- a/modules/mono/editor/GodotTools/GodotTools/Build/BuildOutputView.cs
+++ b/modules/mono/editor/GodotTools/GodotTools/Build/BuildOutputView.cs
@@ -69,42 +69,41 @@ namespace GodotTools.Build
 
         private void LoadIssuesFromFile(string csvFile)
         {
-            using var file = FileAccess.Open(csvFile, FileAccess.ModeFlags.Read)
-            {
-                if (!file)
-                    return;
+            using var file = FileAccess.Open(csvFile, FileAccess.ModeFlags.Read);
 
-                while (!file.EofReached())
-                {
-                    string[] csvColumns = file.GetCsvLine();
+            if (file == null)
+                return;
 
-                    if (csvColumns.Length == 1 && string.IsNullOrEmpty(csvColumns[0]))
-                        return;
+            while (!file.EofReached())
+            {
+                string[] csvColumns = file.GetCsvLine();
 
-                    if (csvColumns.Length != 7)
-                    {
-                        GD.PushError($"Expected 7 columns, got {csvColumns.Length}");
-                        continue;
-                    }
+                if (csvColumns.Length == 1 && string.IsNullOrEmpty(csvColumns[0]))
+                    return;
 
-                    var issue = new BuildIssue
-                    {
-                        Warning = csvColumns[0] == "warning",
-                        File = csvColumns[1],
-                        Line = int.Parse(csvColumns[2]),
-                        Column = int.Parse(csvColumns[3]),
-                        Code = csvColumns[4],
-                        Message = csvColumns[5],
-                        ProjectFile = csvColumns[6]
-                    };
-
-                    if (issue.Warning)
-                        WarningCount += 1;
-                    else
-                        ErrorCount += 1;
-
-                    _issues.Add(issue);
+                if (csvColumns.Length != 7)
+                {
+                    GD.PushError($"Expected 7 columns, got {csvColumns.Length}");
+                    continue;
                 }
+
+                var issue = new BuildIssue
+                {
+                    Warning = csvColumns[0] == "warning",
+                    File = csvColumns[1],
+                    Line = int.Parse(csvColumns[2]),
+                    Column = int.Parse(csvColumns[3]),
+                    Code = csvColumns[4],
+                    Message = csvColumns[5],
+                    ProjectFile = csvColumns[6]
+                };
+
+                if (issue.Warning)
+                    WarningCount += 1;
+                else
+                    ErrorCount += 1;
+
+                _issues.Add(issue);
             }
         }
 
```

## comment by KoBeWi

I think GitHub formatting broke the patch, I can't apply it. Could you attach a file? Thanks for help btw.

## comment by raulsntos

[BuildOutputView.zip](https://github.com/godotengine/godot/files/9490068/BuildOutputView.zip)


## comment by raulsntos

The `include_navigational` and `include_hidden` properties are now ignored because they used to be handled by the non-virtual `Directory::get_next` method. This causes an infinite loop in `converter3to4` which seems to be what's making the CI fail.

## comment by KoBeWi

I totally forgot about `get_next()`. I added a `_get_next()` method for the binding to properly use the include properties.

## comment by reduz

@KoBeWi `thread_local` is useful, but it takes up stack from all threads, so it must be used with care.

## comment by akien-mga

Thanks!

## comment by CsloudX

IMO, I think `File` and `Directory` was a better name than `FileAccess` and `DirAccess`, I don't know why to make this change, is where a disccuss?

| old | new |
| ----- | ---- |
| `var file = File.new()` | `var ??? = FileAcess.new() # file, file_access, access! which name better?` |



And for another reason, in `C#`, `Java`, `Qt`, access file class's name all was `File`, why `Godot` named `FileAccess`?
So I wich it will be named back to `File` and `Directory` please.

OTHER: make such method like `get_md5` to static was a good thing, I like that.

## comment by KoBeWi

The new is actually `FileAccess.open()`, you can no longer create non-opened file/directory, thus the usage has changed.

The old File/Directory were wrappers that used FileAccess/DirAccess under the hood. This PR just strips the wrapping layer and exposes FileAccess/DirAccess directly; the "new" classes just use the core name (changing it is a big deal, because it's used ~2700 times in the engine code, so that would be a lot of changes). Also the new names are more accurate, because you are not creating "File" or "Directory", you are just accessing them from the filesystem. And as I mentioned, the new classes are used a bit differently (no more open/close), so new names signify that.

## comment by dmaz

I don't want to complain but I don't understand the need for a change like this.  Godot is supposed to be in beta now yet this is a pretty significant breaking change.  there is a lot of script that will need to change with this.. it's not just a rename.  the change also touched a lot of src files which of course invalidates all any previous testing during the alpha stage for those.  this breaks style with other classes like ConfigFile.  and with regards to "names are more accurate", who thought that's the case in the first place.  using new() is perfectly consistent with how all classes work in GDScirpt... this new form with the auto new is really not.

Now if this was needed for something that doesn't seem to be described here, well fine.  I think though then that these PRs should include a little blurb explaining the reasoning for the change.  



## comment by KoBeWi

The reason why this PR was created is that the previous Directory/File classes were a workaround for lack of static method bind support in GDScript. This is now possible, so we can get rid of most of the core bind file (which, as you can see in the changes here, just duplicates the methods of original classes and forwards them to a new class). The FileAccess/DirAccess are the only classes that required compatibility breaking, so they were the first ones to be replaced (unfortunately this PR didn't make it before beta1).

This is a breaking change, but not something that can't be fixed easily. Replacing it in my (rather big) project took me ~20 minutes. The API is mostly the same, the only thing that changed is how you create the objects. Also some of the methods are now static, so you can get rid of code like `File.new().file_exists(path)` (which in my case was 90% of the File instances).

## comment by dmaz

Ah! ok, thanks for the reply and I appreciate the explanation.  totally get it now.

## comment by TokisanGames

The documentation hasn't been updated.

DirAccess says to use new() which doesn't work.
```
# Standard
var dir = Directory.new()
dir.open("user://levels")
dir.make_dir("world1")
# Static
Directory.make_dir_absolute("user://levels/world1")

```

## comment by bruvzg

The only reason it was using `File`, instead of `FileAccess` is to be buildable as both GDExtension and module, so it won't work as GDExtension with `get_buffer_bind`.

For consistency with GDExtension, I would rename original to `_get_buffer` and use `get_buffer` instead of  `get_buffer_bind` for a new one. Same for `store_buffe`

## comment by KoBeWi

This have caused soo many changes ;_;

## comment by reduz

When this happens, we generally do the opposite: The underscore version is private and the one that goes to the bindings (that you can re-bind without underscore in the binding name), and C++ remains using the regular one.

This way, you don't need to change any code.

## comment by reduz

same here, you can probably do the bind ones as private, then bind to the proper name.

## comment by reduz

as reference of how its done in other places:
https://github.com/godotengine/godot/blob/master/servers/rendering/rendering_device.h#L1300

## comment by KoBeWi

I did it based on this comment: https://github.com/godotengine/godot/pull/65271#discussion_r962123140

## comment by raulsntos

The bound method should use the enum.

```suggestion
	static Ref<FileAccess> open_bind(const String &p_path, ModeFlags p_mode_flags);
```

## comment by raulsntos

```suggestion
            using var file = FileAccess.Open(csvFile, FileAccess.ModeFlags.Read);
```

## comment by raulsntos

It's important to note here that in C# the file should be disposed and the code examples should be updated to use the `using` statement as a replacement for the `Close` method. The `using` statement is syntax-sugar to call the `Dispose` method, which is what will free the `RefCounted` from C#'s side (otherwise it may still be freed eventually, but you want to make sure the file is closed as soon as possible after you finish using it).

## comment by raulsntos

All C# examples should be updated to add a `using` statement when instantiating a `FileAccess` or `DirAccess` to ensure the `RefCounted` is freed as soon as possible since we no longer have a `Close` method.

```suggestion
		    using var file = FileAccess.Open("user://save_game.dat", File.ModeFlags.Read);
```

I can take care of the C# documentation in a follow up PR if you prefer.

## comment by raulsntos

I wonder why the `default` value has been removed. Probably as a consequence of making these classes abstract.

## comment by KoBeWi

Yeah, the classes need to be instantiated to determine the defaults.

## comment by KoBeWi

> I can take care of the C# documentation in a follow up PR if you prefer.

I'd prefer that.

## comment by akien-mga

Shouldn't those be virtual instead of abstract?

They can be instantiated so (pure) abstract doesn't seem correct to me.

## comment by KoBeWi

I don't know what's the difference. Does virtual also prevent manual instantiation?
I checked how we use abstract and TreeItem is abstract, but you can instantiate it too. Same with SceneTreeTimer.

## comment by akien-mga

Ah so we want to forbid `FileAccess.new()` to force using a create method?

Then abstract might work indeed, but it feels to me like it's exploiting the wrong concept to expose a class which is not abstract nor virtual but just means to be non-instantiable directly.

## comment by reduz

Yes, abstract is good in this case, if we want to provide something towards the future, in this case it will work out better as FileAccessExtension

## comment by bruvzg

Since there is only one place using in the `TextServer`, and it's only an issue for building the same code as module and GDExtension, I guess I can add a `_*_buffer` wrapper methods directly to the `godot-cpp`, or just use `ifdef` in the `TextServer` for this one case.

Currently, `TextServer` is not buildable as GDExtension, due to lack of `TypedArray`s (working on it https://github.com/godotengine/godot-cpp/pull/841), and it's also using inconsistent virtual methods without underscore, so it's gonna need some extra work anyway.

## comment by nikitalita

when this was renamed to `open_internal()`, the `_open()` call below was left in place, which ends up calling `FileAccess::_open()`, which becomes an infinite recursion and causes a stack overflow.

## comment by akien-mga

Fixed by #66485.

@KoBeWi This would have been caught if `_open` was made private, which I think it could be. I see a few more underscore-prefixed methods public in `DirAccess` and `FileAccess`, I would suggest doing another pass on those to see what needs to be public and what can be made private or protected.