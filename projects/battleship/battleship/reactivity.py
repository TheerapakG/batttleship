from tgraphics.reactivity import computed, unref, Ref, Watcher

x = Ref("1")
y = Ref("1")

z = computed(lambda: f"{unref(x)} + {unref(y)}")
watcher = Watcher([z], lambda: print(z.value), trigger_init=True)

x.value = "2"

y.value = "2"

watcher.unwatch()
