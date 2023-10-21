import math
import os
import struct
import time

import numpy as np
from PIL import Image

from .common import ZOOM_4X, BPP_8, BPP_24, BPP_32, PALETTE, ALL_COLOURS, SAFE_COLOURS, \
    to_spectra, SPECTRA_PALETTE, WIN_TO_DOS


def color_distance(c1, c2):
    rmean = (c1.rgb[0] + c2.rgb[0]) / 2.
    r = c1.rgb[0] - c2.rgb[0]
    g = c1.rgb[1] - c2.rgb[1]
    b = c1.rgb[2] - c2.rgb[2]
    return math.sqrt(
        ((2 + rmean) * r * r) +
        4 * g * g +
        (3 - rmean) * b * b)


def find_best_color(x, in_range=SAFE_COLOURS):
    mj, md = 0, 1e100
    for j in in_range:
        c = SPECTRA_PALETTE[j]
        d = color_distance(x, c)
        if d < md:
            mj, md = j, d
    return mj


_remap_cache = {}
_FIX_PALETTE_LOOKUP = {(PALETTE[3 * i], PALETTE[3 * i + 1], PALETTE[3 * i + 2]): i for i in ALL_COLOURS}

def fix_palette(img, sprite_name):
    assert (img.mode == 'P')  # TODO
    pal = tuple(img.getpalette())
    if pal == PALETTE: return img
    print(f'Custom palette in sprite {sprite_name}, converting...')
    # for i in range(256):
    #     if tuple(pal[i * 3: i*3 + 3]) != PALETTE[i * 3: i*3 + 3]:
    #         print(i, pal[i * 3: i*3 + 3], PALETTE[i * 3: i*3 + 3])
    pal_hash = hash(pal)
    remap = _remap_cache.get(pal_hash)
    if remap is None:
        remap = PaletteRemap()
        for i in ALL_COLOURS:
            color = (pal[3 * i], pal[3 * i + 1], pal[3 * i + 2])
            res = _FIX_PALETTE_LOOKUP.get(color)
            if res is None:
                res = find_best_color(to_spectra(*color), in_range=ALL_COLOURS)
            remap.remap[i] = res
        _remap_cache[pal_hash] = remap
    return remap.remap_image(img)


def open_image(filename, *args, **kw):
    return fix_palette(Image.open(filename, *args, **kw), filename)


def convert_image(image):
    if image.mode == 'P':
        return image, BPP_8
    if image.mode == 'RGBA':
        return image, BPP_32
    if image.mode != 'RGB':
        image = image.convert('RGB')
    return img, BPP_24


# Pseudo sprite in grf
class Action:
    def get_data(self):
        raise NotImplemented

    def get_data_size(self):
        raise NotImplemented


class FakeAction:
    def get_data(self):
        return b't'

    def get_data_size(self):
        return 0


# Pseudo sprite (reference) + real sprite in grf
class ResourceAction(Action):
    def __init__(self):
        self.sprite_id = None

    def get_data_size(self):
        return 4

    def get_data(self):
        return struct.pack('<I', self.sprite_id)

    def get_resources(self):
        raise NotImplementedError

    def get_resource_files(self):
        raise NotImplementedError


class SingleResourceAction(ResourceAction):
    def __init__(self, resource):
        super().__init__()
        self.resource = resource

    def get_resources(self):
        return (self.resource, )

    def get_resource_files(self):
        return self.resource.get_resource_files()


class AlternativeSprites(ResourceAction):
    def __init__(self, *sprites):
        assert all(isinstance(s, Sprite) for s in sprites), sprites
        assert len(set((s.zoom, s.bpp) for s in sprites)) == len(sprites), sprites

        super().__init__()
        self.sprites = sprites

    def get_sprite(self, *, zoom=None, bpp=None):
        for s in self.sprites:
            if (zoom is None or s.zoom == zoom) and (bpp is None or s.bpp == bpp):
                return s
        return None

    def get_resources(self):
        return self.sprites

    def get_resource_files(self):
        res = []
        for s in self.sprites:
            res.extend(s.get_resource_files())
        return res


class ResourceFile:
    def __init__(self, path):
        self.path = path


class CodeFile(ResourceFile):
    pass


class PythonFile(CodeFile):
    pass


class SoundFile(ResourceFile):
    pass


THIS_FILE = PythonFile(__file__)


class LoadedResourceFile(ResourceFile):
    def load(self):
        raise NotImplementedError

    def unload(self):
        raise NotImplementedError


class Resource:
    def get_fingerprint(self):
        raise NotImplemented

    def get_resource_files(self):
        return NotImplemented


class Sound(Resource):
    def __init__(self):
        super().__init__()
        self.id = None


class PaletteRemap(Action):
    def __init__(self, ranges=None):
        self.remap = np.arange(256, dtype=np.uint8)
        if ranges:
            self.set_ranges(ranges)

    def get_data(self):
        return b'\x00' + self.remap.tobytes()

    def get_data_size(self):
        return len(self.remap) + 1

    @classmethod
    def from_function(cls, color_func, remap_water=False):
        res = cls()
        for i in SAFE_COLOURS:
            res.remap[i] = find_best_color(color_func(SPECTRA_PALETTE[i]))
        if remap_water:
            for i in WATER_COLOURS:
                res.remap[i] = find_best_color(color_func(SPECTRA_PALETTE[i]))
        return res

    @classmethod
    def from_array(cls, array):
        assert len(array) == 256
        res = cls()
        res.remap = np.array(array, dtype=np.uint8)
        return res

    @classmethod
    def from_buffer(cls, data):
        res = cls()
        res.remap = np.frombuffer(data, dtype=np.uint8)
        return res

    def set_ranges(self, ranges):
        for r in ranges:
            f, t, v = r
            self.remap[f: t + 1] = v

    def remap_image(self, im):
        assert im.mode == 'P', im.mode
        data = np.array(im)
        data = self.remap[data]
        res = Image.fromarray(data)
        res.putpalette(PALETTE)
        return res

    def remap_array(self, a):
        return self.remap[a]


WIN_TO_DOS_REMAP = PaletteRemap.from_array(WIN_TO_DOS)


def combine_fingerprint(*args, **kw):
    res = {}
    for x in args:
        if x is None:
            return None
        res.update(x)

    for k, v in kw.items():
        if callable(v):
            v = v()
            if v is None:
                return None
        res[k] = v
    return res


class Mask:
    class Mode:
        DEFAULT = 0
        OVERDRAW = 1

    def __init__(self, mode=Mode.DEFAULT):
        self.mode = mode

    def get_image(self):
        raise NotImplementedError

    def get_resource_files(self):
        raise NotImplementedError

    def get_fingerprint(self):
        return {
            'class': self.__class__.__name__,
            'mode': self.mode,
        }


class FileMask(Mask):
    def __init__(self, file, x=0, y=0, w=None, h=None, *args, **kw):
        assert(isinstance(file, ImageFile))
        super().__init__(*args, **kw)
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.file = file

    def get_image(self):
        img, bpp = self.file.get_image()
        if self.w is None or self.h is None:
            self.w, self.h = img.size
        img = img.crop((self.x, self.y, self.x + self.w, self.y + self.h))
        return img, bpp

    def __str__(self):
        return str(self.file.path)

    def get_fingerprint(self):
        return combine_fingerprint(
            super().get_fingerprint(),
            x=self.x,
            y=self.y,
            w=self.w,
            h=self.h,
        )

    def get_resource_files(self):
        return (self.file, THIS_FILE)


class ImageMask(Mask):
    def __init__(self, image, *args, **kw):
        assert(isinstance(file, ImageFile))
        super.__init__(*args, **kw)
        self.image = image
        self._converted_image = None

    def get_image(self):
        if self._converted_image is None:
            self._converted_image = convert_image(self.image)
        return self._converted_image

    def __str__(self):
        w, h = self.image.size()
        return f'Image({w}*{h} {self.xofs:+},{self.yofs:+})'

    def get_resource_files(self):
        return (THIS_FILE,)

    def get_fingerprint(self):
        return None


class Sprite(Resource):
    def __init__(self, w, h, *, xofs=0, yofs=0, zoom=ZOOM_4X, bpp=None, mask=None, crop=True):
        if bpp == BPP_8 and mask is not None:
            raise ValueError("8bpp sprites can't have a mask")
        assert mask is None or isinstance(mask, Mask)
        super().__init__()
        self.w = w
        self.h = h
        self.xofs = xofs
        self.yofs = yofs
        self.zoom = zoom
        self.bpp = bpp
        self.mask = mask
        self.crop = crop

    @property
    def name(self):
        return f'{self.w}x{self.h}'

    def get_fingerprint_base(self):
        return combine_fingerprint(
            **{'class': self.__class__.__name__},
            w=self.w,
            h=self.h,
            xofs=self.xofs,
            yofs=self.yofs,
            crop=self.crop,
            mask=None if self.mask is None else self.mask.get_fingerprint,
        )

    def get_fingerprint(self):
        raise NotImplementedError

    def get_image(self):
        raise NotImplementedError

    def draw(self, img):
        raise NotImplementedError

    def get_colourkey(self):
        return None

    # https://github.com/OpenTTD/grfcodec/blob/master/docs/grf.txt
    def get_real_data(self, encoder):
        t0 = time.time()
        img, bpp = self.get_image()
        w, h, xofs, yofs = self.w, self.h, self.xofs, self.yofs
        if w is None:
            w = img.size[0]
        if h is None:
            h = img.size[1]

        encoder.count_loading(time.time() - t0)
        t0 = time.time()

        if self.bpp is None:
            self.bpp = bpp
        npalpha = None

        if bpp != self.bpp:
            print(f'Sprite {self.name} expected {self.bpp}bpp but file is {bpp}bpp, converting.')
            if self.bpp == BPP_24:
                img = img.convert('RGB')
            elif self.bpp == BPP_32:
                img = img.convert('RGBA')
            elif self.bpp == BPP_8:
                p_img = Image.new('P', (16, 16))
                p_img.putpalette(PALETTE)
                img = img.quantize(palette=p_img, dither=0)
        else:
            if bpp == BPP_8:
                img = fix_palette(img, self.name)

        encoder.count_conversion(time.time() - t0)
        t0 = time.time()

        npimg = np.asarray(img)
        colourkey = self.get_colourkey()
        if colourkey is not None:
            if self.bpp == BPP_24:
                npalpha = 255 * np.all(np.not_equal(npimg, colourkey), axis=2)
                npalpha = npalpha.astype(np.uint8, copy=False)
            elif self.bpp == BPP_32:
                if len(colourkey) == 3:
                    colourkey = (*colourkey, 255)
                npalpha = 255 * np.all(np.not_equal(npimg, colourkey), axis=2)
                npalpha = npalpha.astype(np.uint8, copy=False)
            else:
                print(f'Colour key on 8bpp sprites is not supported')

        crop_x = crop_y = 0
        if self.crop and w > 0 and h > 0:
            if npalpha is not None:
                npcheck = npalpha
            elif self.bpp == BPP_32:
                npcheck = npimg[:, :, 3]
            else:
                assert self.bpp == BPP_8, self.bpp
                npcheck = npimg

            cols_used = np.arange(w)[npcheck.any(0)]
            rows_used = np.arange(h)[npcheck.any(1)]
            crop_x = min(cols_used, default=0)
            crop_y = min(rows_used, default=0)
            w = max(cols_used, default=0) - crop_x + 1
            h = max(rows_used, default=0) - crop_y + 1
            xofs += crop_x
            yofs += crop_y

            if npalpha is not None:
                npalpha = npalpha[crop_y: crop_y + h, crop_x: crop_x + w]
            if self.bpp == BPP_8:
                npimg = npimg[crop_y: crop_y + h, crop_x: crop_x + w]
            else:
                npimg = npimg[crop_y: crop_y + h, crop_x: crop_x + w, :]

        info_byte = 0x40
        if self.bpp == BPP_24 or self.bpp == BPP_32:
            if self.bpp == BPP_32:
                npimg = npimg.reshape(w * h, 4)
                rbpp = 4
                info_byte |= 0x1 | 0x2  # rgb, alph

                if npalpha is not None:
                    npimg = npimg[:, :3]
                    npalpha = npalpha.reshape(w * h, 1)
                    stack = [npimg, npalpha]
                else:
                    stack = [npimg]
            else:
                npimg = npimg.reshape(w * h, 3)
                rbpp = 3
                info_byte = 0x1  # rgb

                if npalpha is not None:
                    npalpha = npalpha.reshape(w * h, 1)
                    stack = [npimg, npalpha]
                    rbpp += 1
                    info_byte |= 0x2  # alpha
                else:
                    stack = [npimg]

            mask = self.mask
            if mask is not None:
                mask_img, mask_bpp = mask.get_image()
                if mask_bpp != BPP_8:
                    raise RuntimeError(f'Mask {mask} is not an 8bpp image')
                mask_img = fix_palette(mask_img, mask)
                if mask_img.size != (self.w, self.h):
                    print(mask)
                    raise RuntimeError(f'Mask {mask} size {mask_img.size} doesn'f't match image size {(self.w, self.h)}')
                npmask = np.asarray(mask_img)
                npmask = npmask[crop_y: crop_y + h, crop_x: crop_x + w]
                if mask.mode == Mask.Mode.OVERDRAW:
                    npimg = npimg.copy()
                    stack[0] = npimg
                    npmask = npmask.reshape(w * h)
                    has_mask = (npmask != 0)
                    if npimg.shape[1] == 3:
                        npimg[has_mask] = (127, 127, 127)
                        if npalpha is not None:
                            npalpha = npalpha.reshape(w * h)
                            npalpha[has_mask] = 255
                            npalpha = npalpha.reshape(w * h, 1)
                    else:
                        npimg[has_mask] = (127, 127, 127, 255)
                npmask = npmask.reshape(w * h, 1)
                stack.append(npmask)
                rbpp += 1
                info_byte |= 0x4  # mask

            if len(stack) > 1:
                raw_data = np.concatenate(stack, axis=1)
            else:
                raw_data = stack[0]
            raw_data = raw_data.reshape(w * h * rbpp)

        else:
            info_byte |= 0x4  # pal/mask
            raw_data = npimg.reshape(w * h)

        encoder.count_composing(time.time() - t0)
        data = encoder.sprite_compress(np.ascontiguousarray(raw_data))
        return struct.pack(
            '<BBHHhh',
            info_byte,
            self.zoom,
            h,
            w,
            xofs,
            yofs,
        ) + data

    def get_image_files(self):
        raise NotImplementedError

    def get_resource_files(self):
        res = list(self.get_image_files())
        if self.mask is not None:
            res.extend(self.mask.get_resource_files())
        res.append(THIS_FILE)
        return tuple(res)


class EmptySprite(Sprite):
    def __init__(self):
        super().__init__(1, 1)

    def draw(self, img):
        pass

    def get_real_data(self, encoder):
        return struct.pack(
            '<BBHHhhBB',
            0x4,
            0,
            1,
            1,
            0,
            0,
            1,
            0,
        )

    def get_resource_files(self):
        return (THIS_FILE,)

    def get_fingerprint(self):
        # Empty sprite is always the same so just return the class
        return {'class': self.__class__.__name__}


EMPTY_SPRITE = EmptySprite()


class ImageSprite(Sprite):
    def __init__(self, image, *, mask=None, **kw):
        self._image = convert_image(image)
        super().__init__(*self._image[0].size, bpp=self._image[1], mask=mask, **kw)

    def get_fingerprint(self):
        return None

    def get_image(self):
        return self._image

    def get_image_files(self):
        return ()


class ImageFile(LoadedResourceFile):
    def __init__(self, path, colourkey=None):
        self.path = path
        self.colourkey = colourkey
        self._image = None

    def load(self):
        if self._image is not None:
            return
        img = Image.open(self.path)
        if img.mode == 'P':
            self._image = (img, BPP_8)
        elif img.mode == 'RGB':
            self._image = (img, BPP_24)
        else:
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            self._image = (img, BPP_32)

    def unload(self):
        if self._image is not None:
            self._image[0].close()
            self._image = None


    def get_image(self):
        self.load()
        return self._image


class FileSprite(Sprite):
    def __init__(self, file, x, y, w, h, *, bpp=None, mask=None, **kw):
        assert(isinstance(file, ImageFile))
        super().__init__(w, h, bpp=bpp, mask=mask, **kw)
        self.x = x
        self.y = y
        self.file = file

    @property
    def name(self):
        return f'{self.x},{self.y} {self.w}x{self.h}'

    def get_image(self):
        img, bpp = self.file.get_image()
        if self.w is None or self.h is None:
            self.w, self.h = img.size
        img = img.crop((self.x, self.y, self.x + self.w, self.y + self.h))
        return img, bpp

    def get_colourkey(self):
        return self.file.colourkey

    def get_image_files(self):
        return (self.file,)

    def get_fingerprint(self):
        return combine_fingerprint(
            super().get_fingerprint_base(),
            x=self.x,
            y=self.y,
        )


class RAWSound(Sound):
    def __init__(self, file):
        super().__init__()
        if not isinstance(file, SoundFile):
            file = SoundFile(file)
        self.file = file

    def get_real_data(self, encoder):
        data = open(self.file.path, 'rb').read()
        name = os.path.basename(self.file.path).encode()
        if len(name) > 256:
            name = name[:251] + '_' + name[-4:]
        return struct.pack('<BBB', 0xff, 0xff, len(name)) + name + b'\0' + data

    def get_fingerprint(self):
        return self.file

    def get_resource_files(self):
        return (self.file,)


class NMLFileSpriteWrapper:
    def __init__(self, sprite, file, bit_depth):
        self.sprite = sprite
        self.file = type('Filename', (object, ), {'value': file.path})
        self.bit_depth = bit_depth
        self.mask_file = type('Filename', (object, ), {'value': file.mask}) if file.mask else None
        self.mask_pos = None
        self.flags = type('Flags', (object, ), {'value': 0})

    xpos = property(lambda self: type('XSize', (object, ), {'value': self.sprite.x}))
    ypos = property(lambda self: type('YSize', (object, ), {'value': self.sprite.y}))

    xsize = property(lambda self: type('XSize', (object, ), {'value': self.sprite.w}))
    ysize = property(lambda self: type('YSize', (object, ), {'value': self.sprite.h}))

    xrel = property(lambda self: type('XSize', (object, ), {'value': self.sprite.xofs}))
    yrel = property(lambda self: type('YSize', (object, ), {'value': self.sprite.yofs}))

    def get_resource_files(self):
        return (self.file.value,)
