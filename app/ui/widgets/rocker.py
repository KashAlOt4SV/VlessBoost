"""Small projected rocker frames. The bezel is fixed; the key rotates about X."""
import math
from PIL import Image, ImageDraw, ImageFilter, ImageChops


def render_rocker(size, progress):
    # Supersampling keeps the bevels crisp at desktop DPI sizes.
    factor = 3
    w, h = (n * factor for n in size)
    image = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(image)
    # Layered moulded bezel and recessed socket stay fixed during rotation.
    for inset, colour in ((0,"#16191e"), (.022,"#68717b"), (.047,"#3e454e"),
                          (.082,"#242a32"), (.115,"#080b10")):
        margin = w*inset
        draw.rounded_rectangle((margin, margin, w-1-margin, h-1-margin),
                               radius=max(1,w*(.21-inset)), fill=colour)
    draw.rounded_rectangle((w*.15,h*.075,w*.85,h*.925),radius=w*.10,
                           fill="#020407")
    angle = math.radians(28 * (2*progress-1))
    sine, cosine = math.sin(angle), math.cos(angle)
    halfw, halfh = w*.325, h*.355
    distance = h*1.7

    def project(x, y, z):
        depth = y*sine + z*cosine
        perspective = distance / (distance-depth)
        return (w/2 + x*perspective,
                h/2 + (y*cosine-z*sine)*perspective)

    # Eight chamfered corners describe a solid key, not a cross-faded image.
    chamfer = w*.045
    outline = [(-halfw+chamfer,-halfh), (halfw-chamfer,-halfh),
               (halfw,-halfh+chamfer), (halfw,halfh-chamfer),
               (halfw-chamfer,halfh), (-halfw+chamfer,halfh),
               (-halfw,halfh-chamfer), (-halfw,-halfh+chamfer)]
    front = [project(x,y,w*.19) for x,y in outline]
    back = [project(x,y,-w*.22) for x,y in outline]
    on = progress >= .5
    base = (66, 194, 65) if on else (226, 34, 43)
    def shade(amount):
        return tuple(max(0,min(255,round(c*amount))) for c in base)
    shadow = Image.new("RGBA", (w,h))
    ImageDraw.Draw(shadow).polygon([(x+w*.025,y+h*.035) for x,y in front],
                                   fill=(0,0,0,235))
    image = Image.alpha_composite(image,shadow.filter(ImageFilter.GaussianBlur(w*.045)))
    draw = ImageDraw.Draw(image)
    # Side walls expose the raised edge, opposite in the two end states.
    for i in range(8):
        j = (i+1)%8
        draw.polygon([back[i],back[j],front[j],front[i]], fill=shade(.32 if i in (2,3,4) else .65))
    # Broad chamfer around an inset face gives the key visible thickness.
    inset = [project(x*.83,y*.91,w*.24) for x,y in outline]
    bevel_light = (1.5,1.2,.66,.50,.44,.64,1.10,1.4)
    for i in range(8):
        j=(i+1)%8
        draw.polygon([front[i],front[j],inset[j],inset[i]],fill=shade(bevel_light[i]))
    mask = Image.new("L", (w,h))
    ImageDraw.Draw(mask).polygon(inset, fill=255)
    surface = Image.new("RGBA", (w,h))
    paint = ImageDraw.Draw(surface)
    top = min(y for x,y in inset)
    bottom = max(y for x,y in inset)
    left = min(x for x,y in inset)
    right = max(x for x,y in inset)
    for y in range(max(0,int(top)), min(h,math.ceil(bottom)+1)):
        relative=(y-top)/max(1,bottom-top)
        # Curved plastic catches a broad highlight above the central pivot;
        # the lower half turns into shadow rather than a flat colour block.
        light=(.76 + .32*math.cos((relative-.16)*math.pi)
               + sine*(relative-.5)*.70)
        specular=math.exp(-((relative-(.15-.08*sine))/.075)**2)*.30
        lit=shade(light)
        paint.line((0,y,w,y),fill=tuple(min(255,round(c+(255-c)*specular)) for c in lit)+(255,))
    rounding=Image.new("RGBA",(w,h),(255,255,255,255))
    side=ImageDraw.Draw(rounding)
    for x in range(max(0,int(left)),min(w,math.ceil(right)+1)):
        across=(x-left)/max(1,right-left)
        value=round(255*(.80+.20*math.sin(math.pi*across)))
        side.line((x,0,x,h),fill=(value,value,value,255))
    surface=ImageChops.multiply(surface,rounding)
    image.paste(surface,(0,0),mask)
    draw=ImageDraw.Draw(image)
    draw.line(front+[front[0]],fill=shade(.32),width=max(1,factor//2))
    draw.line([inset[7],inset[0],inset[1]],fill=shade(1.45),width=max(1,factor//2))
    return image.resize(size, Image.Resampling.LANCZOS)
