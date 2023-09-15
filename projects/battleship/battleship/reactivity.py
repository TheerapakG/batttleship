from tgraphics.reactivity import Computed, Ref, Watcher

x = Ref("1")
y = Ref("1")

z = Computed(lambda: x.value + y.value)
watcher = Watcher([z], lambda: print(z.value), trigger_init=True)

x.value = "2"

y.value = "2"

watcher.unwatch()
