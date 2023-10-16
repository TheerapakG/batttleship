from tgraphics.reactivity import computed, unref, Ref, Watcher

x = Ref("1")
y = Ref("1")

# 1 + 1
z = computed(lambda: f"{unref(x)} + {unref(y)}")
print(z.value)

x.value = "2"
# 2 + 1
print(z.value)

y.value = "2"
# 2 + 2
print(z.value)
