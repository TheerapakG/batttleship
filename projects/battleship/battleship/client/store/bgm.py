from pyglet.media import Player, Source

from tgraphics.component import loader

media_player = Player()

menu_bgm = loader.media("bgm/menu.wav", True)


def set_music(music: Source):
    if media_player.source != music:
        media_player.queue(music)
        if media_player.playing:
            media_player.next_source()
        else:
            media_player.play()
