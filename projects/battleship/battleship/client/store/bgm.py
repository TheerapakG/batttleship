from pyglet.media import Player, Source
from tgraphics.reactivity import Ref, computed, unref
from tgraphics.component import loader

media_player = Player()
bgm_volume = Ref(0.5)
menu_bgm = loader.media("bgm/menu.wav", True)


def set_volume(volume):
    media_player.volume = volume


def set_music(music: Source):
    if media_player.source != music:
        media_player.queue(music)
        set_volume(unref(bgm_volume))
        if media_player.playing:
            media_player.next_source()
        else:
            media_player.play()
