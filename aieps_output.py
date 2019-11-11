#!/usr/bin/env python
"""
Mainly written by Andras Prim github_at_primandras.hu

Arc to bezier converting method is ported from:
http://code.google.com/p/core-framework/source/browse/trunk/plugins/svg.js
written by Angel Kostadinov, with MIT license
"""

try:
	from lxml import etree as ET
except Exception:
	import xml.etree.ElementTree as ET

import re
import math

def wrap(text, width):
    """ A word-wrap function that preserves existing line breaks """
    retstr = ""
    for word in text.split(' '):
        if len(retstr)-retstr.rfind('\n')-1 + len(word.split('\n',1)[0]) >= width:
            retstr += ' \n' + word
        else:
            retstr += ' ' + word
    return retstr

def css2dict(css):
    """returns a dictionary representing the given css string"""
    cssdict = {}
    if None == css:
        return cssdict
    for pair in css.split(';'): #TODO: what about escaped separators
        if pair.find(':') >= 0:
            key, value = pair.split(':')
            cssdict[ key.strip() ] = value.strip()
    return cssdict

def cssColor2Eps(cssColor, colors='RGB'):
    """converts css color definition (a hexa code with leading #)
    to eps color definition"""
    r = float(int(cssColor[1:3],16)) / 255
    g = float(int(cssColor[3:5],16)) / 255
    b = float(int(cssColor[5:7],16)) / 255
    if colors == 'RGB':
        return "%f %f %f" % (r, g, b)
    elif colors == 'CMYKRGB':
        if (r == 0) and (g == 0) and (b == 0):
            c = 0
            m = 0
            y = 0
            k = 1
        else:
            c = 1 - r
            m = 1 - g
            y = 1 - b

            # extract out k [0,1]
            min_cmy = min(c, m, y)
            c = (c - min_cmy) / (1 - min_cmy)
            m = (m - min_cmy) / (1 - min_cmy)
            y = (y - min_cmy) / (1 - min_cmy)
            k = min_cmy

        return "%f %f %f %f %f %f %f" % (c, m, y, k, r, g, b)

class svg2eps:
    def __init__(self, filename=None):
        self.filename = filename
        self.svg = None
        self.rePathDSplit = re.compile('[^a-zA-Z0-9.-]+')
        self.reTransformFind = re.compile('([a-z]+)\\(([^)]+)\\)')
        self.reNumberFind = re.compile('[0-9.eE+-]+')
        # must update reNumberUnitFind, if e is a valid character in a unit
        self.reNumberUnitFind = re.compile('([0-9.eE+-]+)([a-z]*)')
        # px to pt conversion rate varies based on inkscape versions, it is added during parsing
        self.toPt = {'in': 72.0, 'pt': 1.0, 'mm': 2.8346456695, 'cm': 28.346456695, 'm': 2834.6456695, 'pc': 12.0}

    def unitConv(self, string, toUnit):
        match = self.reNumberUnitFind.search(string)
        number = float(match.group(1))
        unit = match.group(2)
        if unit not in self.toPt:
            unit = 'uu'

        if unit == toUnit:
            return number
        else:
            return number * self.toPt[unit] / self.toPt[toUnit]

    def lengthConv(self, svgLength):
        """converts svgLength to eps length using the current transformation matrix"""
        matrix = self.matrices[-1]
        epsx = matrix[0] * svgLength
        epsy = matrix[1] * svgLength

        return math.sqrt(epsx*epsx + epsy*epsy)

    def coordConv(self, svgx, svgy, relative=False):
        """converts svgx, svgy coordinates to eps coordinates using the current transformation matrix"""
        if relative:
            svgx = float(svgx) + self.curPoint[0]
            svgy = float(svgy) + self.curPoint[1]
        else:
            svgx = float(svgx)
            svgy = float(svgy)
        matrix = self.matrices[-1]
        epsx = matrix[0] * svgx + matrix[2] * svgy + matrix[4]
        epsy = matrix[1] * svgx + matrix[3] * svgy + matrix[5]

        return (epsx, epsy)

    def matrixMul(self, matrix, matrix2):
        """multiplies matrix with matrix2"""
        matrix0 = matrix[:]
        matrix[0] = matrix0[0] * matrix2[0] + matrix0[2]*matrix2[1] # + matrix0[4]*0
        matrix[1] = matrix0[1] * matrix2[0] + matrix0[3]*matrix2[1] # + matrix0[5]*0
        matrix[2] = matrix0[0] * matrix2[2] + matrix0[2]*matrix2[3] # + matrix0[4]*0
        matrix[3] = matrix0[1] * matrix2[2] + matrix0[3]*matrix2[3] # + matrix0[5]*0
        matrix[4] = matrix0[0] * matrix2[4] + matrix0[2]*matrix2[5] + matrix0[4]
        matrix[5] = matrix0[1] * matrix2[4] + matrix0[3]*matrix2[5] + matrix0[5]


    def alert(self, string, elem):
        """adds an alert to the collection"""
        if not string in self.alerts:
            self.alerts[string] = set()
        elemId = elem.get('id')
        if elemId != None:
            self.alerts[string].add(elemId)

    def showAlerts(self):
        """show alerts collected by the alert() function"""
        for string, ids in self.alerts.iteritems():
            idstring = ', '.join(ids)
            print(string, idstring)

    def elemSvg(self, elem):
        """handles the <svg> element"""
        # DPI changed in inkscape 0.92, so set the px-to-pt rate based on inkscape version
        self.toPt['px'] = 1
        inkscapeVersionString = elem.get('{http://www.inkscape.org/namespaces/inkscape}version', '0.92.0')
        mobj = re.match(r'(\d+)\.(\d+)', inkscapeVersionString)
        if mobj != None:
            major = int(mobj.group(1))
            minor = int(mobj.group(2))
            if major == 0 and minor < 92:
                self.toPt['px'] = 1

        # by default (without viewbox definition) user unit = pixel
        self.toPt['uu'] = self.toPt['px']
        self.docWidth = self.unitConv(elem.get('width'), 'pt')
        self.docHeight = self.unitConv(elem.get('height'), 'pt')

        viewBoxString = elem.get('viewBox')
        if viewBoxString != None:
            viewBox = viewBoxString.split(' ')
            # theoretically width and height scaling factor could be different,
            # but this script does not support it
            widthUu = float(viewBox[2]) - float(viewBox[0])
            self.toPt['uu'] = self.docWidth / widthUu

        # transform svg units to eps default pt
        scale = self.toPt['uu']
        self.matrices = [ [scale, 0, 0, -scale, 0, self.docHeight] ]


    def gradientFill(self, elem, gradientId):
        """constructs a gradient instance definition in self.gradientOp"""
        if gradientId not in self.gradients:
            self.alert("fill gradient not defined: "+gradientId, elem )
            return
        gradient = self.gradients[gradientId]
        transformGradient = gradient
        while 'href' in gradient:
            gradientId = gradient['href']
            gradient = self.gradients[gradientId]
        if 'matrix' in transformGradient:
            self.matrices.append( self.matrices[-1][:] )
            self.matrixMul(self.matrices[-1],transformGradient['matrix'])

        if 'linear' == transformGradient['type']:
            gradient['linUseCount'] += 1
            x1, y1 = self.coordConv(transformGradient['x1'], transformGradient['y1'])
            x2, y2 = self.coordConv(transformGradient['x2'], transformGradient['y2'])
            deltax = x2 - x1
            deltay = y2 - y1
            length = math.sqrt( deltax*deltax + deltay*deltay )
            angle = math.atan2(deltay, deltax)*180/math.pi

        elif 'radial' == transformGradient['type']:
            gradient['radUseCount'] += 1
            cx, cy = self.coordConv(transformGradient['cx'], transformGradient['cy'])
            # fx, fy = self.coordConv(transformGradient['fx'], transformGradient['fy'])
            rx, ry = self.coordConv(transformGradient['cx'] + transformGradient['r'], transformGradient['cy'])
            r = math.sqrt( (rx-cx)*(rx-cx) + (ry-cy)*(ry-cy))

        if 'matrix' in transformGradient:
            self.matrices.pop()


        if 'linear' == transformGradient['type']:
            #endPathSegment() will substitute appropriate closeOp in %%s
            self.gradientOp = "\nBb 1 (l_%s) %f %f %f %f 1 0 0 1 0 0 Bg %%s 0 BB" % \
                (gradientId, x1, y1, angle, length)
        elif 'radial' == transformGradient['type']:
            self.gradientOp = "\nBb 1 (r_%s) %f %f 0 %f 1 0 0 1 0 0 Bg %%s 0 BB" % \
                (gradientId, cx, cy, r)
            self.alert("radial gradients will appear circle shaped", elem)



    def pathStyle(self, elem):
        """handles the style attribute in svg element"""
        if self.clipPath:
            self.closeOp = 'h n'
            return

        css = self.cssStack[-1]
        if 'stroke' in css and css['stroke'] != 'none':
            self.closeOp = 's'
            self.pathCloseOp = 's'
            if '#' == css['stroke'][0]:
                self.epspath += ' ' + cssColor2Eps(css['stroke']) + ' XA'
            elif 'url' == css['stroke'][0:3]:
                self.alert("gradient strokes not supported", elem)
        if 'fill' in css and css['fill'] != 'none':
            if self.closeOp == 's':
                self.closeOp = 'b'
            else:
                self.closeOp = 'f'
            if '#' == css['fill'][0]:
                self.epspath += ' ' + cssColor2Eps(css['fill']) + ' Xa'
            elif 'url' == css['fill'][0:3]:
                self.gradientFill(elem, css['fill'][5:-1])


        if 'fill-rule' in css:
            if css['fill-rule'] == 'evenodd':
                self.epspath += " 1 XR"
            else:
                self.epspath += " 0 XR"
        if 'stroke-width' in css:
            self.epspath += " %f w" % (self.lengthConv(self.unitConv(css['stroke-width'], 'uu')), )
        if 'stroke-linecap' in css:
            if css['stroke-linecap'] == 'butt':
                self.epspath += " 0 J"
            elif css['stroke-linecap'] == 'round':
                self.epspath += " 1 J"
            elif css['stroke-linecap'] == 'square':
                self.epspath += " 2 J"
        if 'stroke-linejoin' in css:
            if css['stroke-linejoin'] == 'miter':
                self.epspath += " 0 j"
            elif css['stroke-linejoin'] == 'round':
                self.epspath += " 1 j"
            elif css['stroke-linejoin'] == 'bevel':
                self.epspath += " 2 j"
        if 'stroke-miterlimit' in css:
            self.epspath += " " + css['stroke-miterlimit'] + " M"
        if 'stroke-dasharray' in css:
            phase = 0
            if css['stroke-dasharray'] == 'none':
                dashArray = []
            else:
                dashArray = list(map(lambda x: "%f" % (self.lengthConv(float(x)),), css['stroke-dasharray'].split(',')))
                if 'stroke-dashoffset' in css:
                    phase = float(css['stroke-dashoffset'])

            self.epspath += ' [ %s ] %f d' % (' '.join(dashArray), phase)



    def endPathSegment(self, elem):
        """should be called when a path segment end is reached in a <path> element"""
        if self.removeStrayPoints and self.segmentCommands <= 1:
            self.alert("removing stray point", elem)
            self.epspath = self.epspath[:self.segmentStartIndex]
            return
        if self.autoClose and (self.closeOp == 'f' or self.closeOp == 'b'):
            autoClose = True
        else:
            autoClose = False

        if self.pathExplicitClose or autoClose:
            closeOp = self.closeOp
        else:
            closeOp = self.closeOp.upper()

        if self.pathCurSegment == self.pathSegmentNum and self.gradientOp != None:
            closeOp = self.gradientOp % (closeOp,)

        if self.lastBegin != None:
            if (self.pathExplicitClose or autoClose):
                if abs(self.curPoint[0] - self.lastBegin[0]) + \
                    abs(self.curPoint[1] - self.lastBegin[1]) > self.closeDist:
                    x, y = self.coordConv(self.lastBegin[0], self.lastBegin[1])
                    self.epspath += ' %f %f l' % (x, y)

            self.epspath += ' ' + closeOp + '\n'

            if self.pathExplicitClose:
                self.curPoint = self.lastBegin

        self.lastBegin = None

    def elemPath(self, elem, pathData=None):
        """handles <path> svg element"""
        if None == pathData:
            pathData = elem.get('d')
        self.pathSegmentNum = pathData.count("m") + pathData.count("M")
        self.pathCurSegment = 0
        self.epspath = ''
        self.segmentStartIndex = 0 # index in self.epspath of first character of current path segment
        self.segmentCommands = 0 # number of handled commands (including first moveto) in current paths segment
        self.closeOp = 'n' # pathStyle(elem) will modify this
        self.gradientOp = None
        self.pathExplicitClose = False
        self.epspath += '\n%AI3_Note: ' + elem.get('id') + '\n'
        self.pathStyle(elem)

        tokens = self.rePathDSplit.split(pathData)
        i = 0
        cmd = '' # path command
        self.curPoint = (0,0)
        self.lastBegin = None

        while i < len(tokens):
            token = tokens[i]
            if token in ['m', 'M', 'c', 'C', 'l', 'L', 'z', 'Z', 'a', 'A', 'q', 'Q', 'h', 'H', 'v', 'V']:
                cmd = token
                i += 1
            elif token.isalpha():
                self.alert('unhandled path command: %s' % (token,), elem)
                cmd = ''
                i += 1
            else: # coordinates after a moveto are assumed to be lineto
                if 'm' == cmd:
                    cmd = 'l'
                elif 'M' == cmd:
                    cmd = 'L'

            if ('M' == cmd or 'm' == cmd) :
                if self.pathCurSegment > 0:
                    self.endPathSegment(elem)
                self.pathCurSegment += 1
                self.pathExplicitClose = False

            if 'M' == cmd or 'm' == cmd:
                if 'M' == cmd or ('m' == cmd and i == 1):
                    self.curPoint = (float(tokens[i]), float(tokens[i+1]))
                else:
                    self.curPoint = (self.curPoint[0] + float(tokens[i]), self.curPoint[1] + float(tokens[i+1]))

                self.segmentStartIndex = len(self.epspath)
                x, y = self.coordConv(self.curPoint[0], self.curPoint[1])
                self.epspath += ' %f %f' % (x, y)
                i += 2
                self.lastBegin = self.curPoint
                self.epspath += ' m'
                self.segmentCommands = 1
            elif 'L' == cmd or 'l' == cmd:
                if 'L' == cmd:
                    self.curPoint = (float(tokens[i]), float(tokens[i+1]))
                else:
                    self.curPoint = (self.curPoint[0] + float(tokens[i]), self.curPoint[1] + float(tokens[i+1]))
                x, y = self.coordConv(self.curPoint[0], self.curPoint[1])
                self.epspath += ' %f %f' % (x, y)
                i += 2
                self.epspath += ' l'
                self.segmentCommands += 1
            elif cmd in ['H', 'h', 'V', 'v']:
                if 'H' == cmd:
                    self.curPoint = (float(tokens[i]), self.curPoint[1])
                elif 'h' == cmd:
                    self.curPoint = (self.curPoint[0] + float(tokens[i]), self.curPoint[1])
                elif 'V' == cmd:
                    self.curPoint = (self.curPoint[0], float(tokens[i]))
                elif 'v' == cmd:
                    self.curPoint = (self.curPoint[0], self.curPoint[1] + float(tokens[i]))
                x, y = self.coordConv(self.curPoint[0], self.curPoint[1])
                self.epspath += ' %f %f' % (x, y)
                i += 1
                self.epspath += ' l'
                self.segmentCommands += 1
            elif 'C' == cmd:
                for j in range(2):
                    x, y = self.coordConv(tokens[i], tokens[i+1])
                    self.epspath += ' %f %f' % (x, y)
                    i += 2
                self.curPoint = (float(tokens[i]), float(tokens[i+1]))
                x, y = self.coordConv(self.curPoint[0], self.curPoint[1])
                self.epspath += ' %f %f' % (x, y)
                i += 2
                self.epspath += ' c'
                self.segmentCommands += 1
            elif 'c' == cmd:
                for j in range(2):
                    x, y = self.coordConv(self.curPoint[0] + float(tokens[i]), self.curPoint[1] +float(tokens[i+1]))
                    self.epspath += ' %f %f' % (x, y)
                    i += 2
                self.curPoint = (self.curPoint[0] + float(tokens[i]), self.curPoint[1] + float(tokens[i+1]))
                x, y = self.coordConv(self.curPoint[0], self.curPoint[1])
                self.epspath += ' %f %f' % (x, y)
                i += 2
                self.epspath += ' c'
                self.segmentCommands += 1
            elif 'Q' == cmd:
                #export quadratic Bezier as cubic
                x, y = self.coordConv(tokens[i], tokens[i+1])
                self.epspath += ' %f %f %f %f' % (x, y, x, y)
                i += 2
                self.curPoint = (float(tokens[i]), float(tokens[i+1]))
                x, y = self.coordConv(self.curPoint[0], self.curPoint[1])
                self.epspath += ' %f %f' % (x, y)
                i += 2
                self.epspath += ' c'
                self.segmentCommands += 1
            elif 'q' == cmd:
                x, y = self.coordConv(self.curPoint[0] + float(tokens[i]), self.curPoint[1] +float(tokens[i+1]))
                self.epspath += ' %f %f %f %f' % (x, y, x, y)
                i += 2
                self.curPoint = (self.curPoint[0] + float(tokens[i]), self.curPoint[1] + float(tokens[i+1]))
                x, y = self.coordConv(self.curPoint[0], self.curPoint[1])
                self.epspath += ' %f %f' % (x, y)
                i += 2
                self.epspath += ' c'
                self.segmentCommands += 1
            elif 'A' == cmd or 'a' == cmd:
                self.alert("elliptic arcs are converted to bezier curves", elem)

# Angel Kostadinov begin
                r1 = abs(float(tokens[i]))
                r2 = abs(float(tokens[i+1]))
                psai = float(tokens[i+2])
                largeArcFlag = int(tokens[i + 3])
                fS = int(tokens[i+4])
                rx = self.curPoint[0]
                ry = self.curPoint[1]
                if 'A' == cmd:
                    cx, cy = (float(tokens[i+5]), float(tokens[i+6]))
                else:
                    cx, cy = (self.curPoint[0] +float(tokens[i+5]), self.curPoint[1] +float(tokens[i+6]))

                if r1 > 0 and r2 > 0:
                    ctx = (rx - cx) / 2
                    cty = (ry - cy) / 2
                    cpsi = math.cos(psai*math.pi/180)
                    spsi = math.sin(psai*math.pi/180)
                    rxd = cpsi*ctx + spsi*cty
                    ryd = -1*spsi*ctx + cpsi*cty
                    rxdd = rxd * rxd
                    rydd = ryd * ryd
                    r1x = r1 * r1
                    r2y = r2 * r2
                    lamda = rxdd/r1x + rydd/r2y

                    if lamda > 1:
                        r1 = math.sqrt(lamda) * r1
                        r2 = math.sqrt(lamda) * r2
                        sds = 0
                    else:
                        seif = 1
                        if largeArcFlag == fS:
                            seif = -1
                        sds = seif * math.sqrt((r1x*r2y - r1x*rydd - r2y*rxdd) / (r1x*rydd + r2y*rxdd))

                    txd = sds*r1*ryd / r2
                    tyd = -1 * sds*r2*rxd / r1
                    tx = cpsi*txd - spsi*tyd + (rx+cx)/2
                    ty = spsi*txd + cpsi*tyd + (ry+cy)/2
                    rad = math.atan2((ryd-tyd)/r2, (rxd-txd)/r1) - math.atan2(0, 1)
                    if rad >= 0:
                        s1 = rad
                    else:
                        s1 = 2 * math.pi + rad
                    rad = math.atan2((-ryd-tyd)/r2, (-rxd-txd)/r1) - math.atan2((ryd-tyd)/r2, (rxd-txd)/r1)
                    if rad >= 0:
                        dr = rad
                    else:
                        dr = 2 * math.pi + rad

                    if fS==0 and dr > 0:
                        dr -= 2*math.pi
                    elif fS==1 and dr < 0:
                        dr += 2*math.pi

                    sse = dr * 2 / math.pi
                    if sse < 0:
                        seg = math.ceil(-1*sse)
                    else:
                        seg = math.ceil(sse)
                    segr = dr / seg
                    t = 8.0/3.0 * math.sin(segr/4) * math.sin(segr/4) / math.sin(segr/2)
                    cpsir1 = cpsi * r1
                    cpsir2 = cpsi * r2
                    spsir1 = spsi * r1
                    spsir2 = spsi * r2
                    mc = math.cos(s1)
                    ms = math.sin(s1)
                    x2 = rx - t * (cpsir1*ms + spsir2*mc)
                    y2 = ry - t * (spsir1*ms - cpsir2*mc)

                    for n in range(int(math.ceil(seg))):
                        s1 += segr
                        mc = math.cos(s1)
                        ms = math.sin(s1)

                        x3 = cpsir1*mc - spsir2*ms + tx
                        y3 = spsir1*mc + cpsir2*ms + ty
                        dx = -t * (cpsir1*ms + spsir2*mc)
                        dy = -t * (spsir1*ms - cpsir2*mc)

                        cx1, cy1 = self.coordConv(x2,y2)
                        cx2, cy2 = self.coordConv(x3-dx,y3-dy)
                        cx3, cy3 = self.coordConv(x3,y3)

                        self.epspath += " %f %f %f %f %f %f c" % (cx1, cy1, cx2, cy2, cx3, cy3)

                        x2 = x3 + dx
                        y2 = y3 + dy
                else:
                    # case when one radius is zero: this is a simple line
                    x, y = self.coordConv(cx, cy)
                    self.epspath += ' %f %f l' % (x, y)

# Angel Kostadinov end
                self.segmentCommands += 1
                i += 7
                self.curPoint= (cx, cy)

            elif 'z' == cmd:
                self.pathExplicitClose = True
                cmd = ''
            else:
                i += 1

        self.endPathSegment(elem)

        if self.pathSegmentNum > 1:
            self.epspath = " *u\n" + self.epspath + "\n*U "
        self.epsLayers += "\n" + wrap(self.epspath, 70) + "\n"

    def elemRect(self, elem):
        x = float(elem.get('x'))
        y = float(elem.get('y'))
        width = float(elem.get('width'))
        height = float(elem.get('height'))

        # construct an svg <path> d attribute, and call self.elemPath()
        pathData = ""
        rx = elem.get('rx')
        ry = elem.get('ry')
        if None == rx and None == ry:
            rx = 0
            ry = 0
        else:
            # if only one radius is given, it means both are the same
            if None == rx:
                rx = float(ry)
            else:
                rx = float(rx)
            if None == ry:
                ry = float(rx)
            else:
                ry = float(ry)

        if rx == 0 and ry == 0:
            pathData = "M %f %f %f %f %f %f %f %f z" % (x,y, x+width,y, x+width, y+height, x, y+height)
        else:
            pathData = "M %f %f A %f %f 0 0 1 %f %f" % (x, y+ry, rx,ry, x+rx, y)
            pathData += " L %f %f A %f %f 0 0 1 %f %f" % (x+width-rx, y, rx,ry, x+width, y+ry)
            pathData += " L %f %f A %f %f 0 0 1 %f %f" % (x+width, y+height-ry, rx,ry, x+width-rx, y+height)
            pathData += " L %f %f A %f %f 0 0 1 %f %f z" % (x+rx, y+height, rx,ry, x, y+height-ry)
        self.elemPath(elem, pathData)




    def attrTransform(self, matrix, transform):
        """transforms matrix using svg transform attribute"""
        for ttype, targs in self.reTransformFind.findall(transform):
            targs = list(map(lambda x: float(x), self.reNumberFind.findall(targs)))
            if ttype == 'matrix':
                newmatrix = [ targs[0], targs[1],
                             targs[2], targs[3],
                             targs[4], targs[5] ]
                self.matrixMul(matrix, newmatrix)
            elif ttype == 'translate':
                tx = targs[0]
                ty = targs[1] if len(targs) > 1 else 0
                newmatrix = [ 1, 0, 0, 1, tx, ty ]
                self.matrixMul(matrix, newmatrix)
            elif ttype == 'scale':
                sx = targs[0]
                sy = targs[1] if len(targs) > 1 else sx
                newmatrix = [ sx, 0, 0, sy, 0, 0 ]
                self.matrixMul(matrix, newmatrix)
            elif ttype == 'rotate':
                if len(targs) == 1:
                    alpha = targs[0]
                    newmatrix = [ math.cos(alpha), math.sin(alpha),
                                 -math.sin(alpha), math.cos(alpha),
                                 0, 0]
                    self.matrixMul(matrix, newmatrix)
                else:
                    alpha = targs[0]
                    newmatrix = [ 1, 0, 0, 1, targs[1], targs[2] ]
                    self.matrixMul(matrix, newmatrix)
                    newmatrix = [ math.cos(alpha), math.sin(alpha),
                                 -math.sin(alpha), math.cos(alpha),
                                 0, 0]
                    self.matrixMul(matrix, newmatrix)
                    newmatrix = [ 1, 0, 0, 1, -targs[1], -targs[2] ]
                    self.matrixMul(matrix, newmatrix)
            elif ttype == 'skewX' or ttype == 'skewY':
                self.alert("skewX and skewY transformations are not supported", elem)
            else:
                print('unknown transform type: ', ttype)
        return matrix

    def elemGradient(self, elem, grType):
        """handles <linearGradient> and <radialGradient> svg elements"""
        elemId  = elem.get('id')
        if elemId != None:
            self.curGradientId = elemId
            self.gradients[elemId] = {'stops': [], 'linUseCount': 0, 'radUseCount': 0, 'type': grType}
            if 'linear' == grType:
                x1 = elem.get('x1')
                if None != x1:
                    self.gradients[elemId]['x1'] = float(x1)
                    self.gradients[elemId]['y1'] = float(elem.get('y1'))
                    self.gradients[elemId]['x2'] = float(elem.get('x2'))
                    self.gradients[elemId]['y2'] = float(elem.get('y2'))
            elif 'radial' == grType:
                cx = elem.get('cx')
                if None != cx:
                    self.gradients[elemId]['cx'] = float(cx)
                    self.gradients[elemId]['cy'] = float(elem.get('cy'))
                    self.gradients[elemId]['fx'] = float(elem.get('fx'))
                    self.gradients[elemId]['fy'] = float(elem.get('fy'))
                    self.gradients[elemId]['r'] = float(elem.get('r'))

            transform = elem.get('gradientTransform')
            if None != transform:
                self.gradients[elemId]['matrix'] = self.attrTransform([1, 0, 0, 1, 0, 0], transform)

            href = elem.get('{http://www.w3.org/1999/xlink}href')
            if None != href:
                self.gradients[elemId]['href'] = href[1:]


    def elemStop(self, elem):
        """handles <stop> (gradient stop) svg element"""
        style = css2dict(elem.get('style'))
        color = cssColor2Eps(style['stop-color'], 'CMYKRGB')
        offset = float(elem.get('offset')) * 100
        self.gradients[self.curGradientId]['stops'].append( (offset, color) )

    def gradientSetup(self):
        """writes used gradient definitions into self.epsSetup"""
        gradientNum = 0
        epsGradients = ""
        for gradientId, gradient in self.gradients.items():

            if gradient['linUseCount'] > 0:
                gradientNum += 1
                epsGradients += ("\n%%AI5_BeginGradient: (l_%s)" + \
                    "\n(l_%s) 0 %d Bd\n[\n") % \
                    (gradientId, gradientId, len(gradient['stops']))
                gradient['stops'].sort(key=lambda x: x[0], reverse=True)

                for offset, color in gradient['stops']:
                    epsGradients += "%s 2 50 %f %%_Bs\n" % (color, offset)
                epsGradients += "BD\n%AI5_EndGradient\n"

            if gradient['radUseCount'] > 0:
                gradientNum += 1
                epsGradients += ("\n%%AI5_BeginGradient: (r_%s)" + \
                    "\n(r_%s) 1 %d Bd\n[\n") % \
                    (gradientId, gradientId, len(gradient['stops']))
                gradient['stops'].sort(key=lambda x: x[0])

                for offset, color in gradient['stops']:
                    epsGradients += "%s 2 50 %f %%_Bs\n" % (color, offset)
                epsGradients += "BD\n%AI5_EndGradient\n"

        if gradientNum > 0:
            self.epsSetup += ("\n%d Bn\n" % gradientNum) + epsGradients


    def layerStart(self, elem):
        self.epsLayers += '\n\n%AI5_BeginLayer\n'
        layerName = elem.get('{http://www.inkscape.org/namespaces/inkscape}label')
        layerName = "".join(map(lambda x: '_' if ord(x)<32 or ord(x) > 127 else x, layerName))
        self.epsLayers += '1 1 1 1 0 0 %d 0 0 0 Lb\n(%s) Ln\n' % \
            (self.layerColor, layerName)
        self.layerColor = (self.layerColor + 1) % 27

    def elemUse(self, elem):
        """handles a <use> svg element"""
        x = self.unitConv(elem.get('x'), 'uu')
        if x == None:
            x = 0
        y = self.unitConv(elem.get('y'), 'uu')
        if y == None:
            y = 0

        if x != 0 or y != 0:
            self.matrices.append( self.matrices[-1][:] )
            self.attrTransform(self.matrices[-1], "translate(%f %f)" % (x, y))

        href = elem.get('{http://www.w3.org/1999/xlink}href')
        usedElem = self.root.find(".//*[@id='%s']" % (href[1:],))
        if usedElem != None:
            self.walkElem(usedElem)
        else:
            self.alert("used Elem not found: " + href, elem)

        if x != 0 or y != 0:
            self.matrices.pop()

    # def elemNamedView(self, elem):
    #     """handles a <sodipodi:namedview> svg element"""
    #     newDocumentUnit = elem.get('{http://www.inkscape.org/namespaces/inkscape}document-units')
    #     if newDocumentUnit in self.toPt and newDocumentUnit != self.documentUnit:
    #         if len(self.matrices) > 0:
    #             # recalculate scaling transformation to new document unit
    #             scale = self.toPt[newDocumentUnit] / self.toPt[self.documentUnit]
    #             self.matrices[-1][0] = scale * self.matrices[-1][0]
    #             self.matrices[-1][3] = scale * self.matrices[-1][3]
    #         self.documentUnit = newDocumentUnit

    def walkElem(self, elem):
        if '}' in elem.tag:
            uri, shortTag = elem.tag.split('}')
        else:
            shortTag = elem.tag
            uri = ''

        transform = elem.get('transform')
        clipPath = elem.get('clip-path')
        cssNew = css2dict(elem.get('style'))
        css = self.cssStack[-1].copy()
        css.update(cssNew)
        self.cssStack.append(css)
        if self.removeInvisible:
            if 'visibility' in css and (css['visibility'] == 'hidden' or css['visibility'] == 'collapse'):
                return
            if 'display' in css and css['display'] == 'none':
                return
            if shortTag in ('path', 'rect'):
                if 'opacity' in css and css['opacity'] == '0':
                    return
                stroke = False
                if 'stroke' in css and 'none' != css['stroke']:
                    stroke = True
                    if 'stroke-opacity' in css and css['stroke-opacity'] == '0':
                        stroke = False
                    if 'stroke-width' in css and css['stroke-width'] == '0':
                        stroke = False
                fill = False
                if 'fill' in css and 'none' != css['fill']:
                    fill = True
                    if 'fill-opacity' in css and css['fill-opacity'] == '0':
                        stroke = False
                if stroke == False and fill == False:
                    return


        if transform != None:
            self.matrices.append( self.matrices[-1][:] )
            self.attrTransform(self.matrices[-1], transform)

        if None != clipPath:
            clipId = clipPath[5:-1]
            clipElem = self.root.find(".//*[@id='%s']" % (clipId,))
            if clipElem == None:
                self.alert('clipPath not found', elem)
                clipPath = None
            else:
                self.epsLayers += "\nq\n"
                clipPathSave= self.clipPath
                self.clipPath = True
                self.walkElem(clipElem)
                self.clipPath = clipPathSave
                self.epsLayers += ' W'

        if 'svg' == shortTag:
            self.elemSvg(elem)
        elif 'path' == shortTag:
            # do not output paths that are in defs
            # if they are referenced, they will be used there
            if self.section != 'defs':
                self.elemPath(elem)
        elif 'rect' == shortTag:
            if self.section != 'defs':
                self.elemRect(elem)
        elif 'linearGradient' == shortTag:
            self.elemGradient(elem, 'linear')
        elif 'radialGradient' == shortTag:
            self.elemGradient(elem, 'radial')
        elif 'stop' == shortTag:
            self.elemStop(elem)
        elif 'g' == shortTag:
            if 'layer' == elem.get('{http://www.inkscape.org/namespaces/inkscape}groupmode'):
                self.layerStart(elem)
            elif None == clipPath: # clipping makes a group anyway
                self.epsLayers += '\nu\n'
        elif 'use' == shortTag:
            self.elemUse(elem)
        elif 'defs' == shortTag:
            self.section = shortTag
        elif 'namedview' == shortTag:
            self.section = shortTag
        else:
            self.alert("unhandled elem: " + shortTag, elem)


        for child in list(elem):
            self.walkElem(child)

        if None != clipPath:
            self.epsLayers += "\nQ\n"

        if 'g' == shortTag:
            if 'layer' == elem.get('{http://www.inkscape.org/namespaces/inkscape}groupmode'):
                self.epsLayers += '\nLB\n%AI5_EndLayer\n'
            elif None == clipPath:
                self.epsLayers += '\nU\n'
        elif shortTag in ('defs', 'namedview'):
            self.section = None

        if transform != None:
            self.matrices.pop()

        self.cssStack.pop()

    def convert(self, svg = None):
        self.alerts = {}
        if None != svg:
            self.svg = svg
        if None == self.svg and None != self.filename:
            fd = open(self.filename, 'rb')
            self.svg = fd.read()
            fd.close()

        self.autoClose = True # TODO: make it optional
        self.removeInvisible = True # TODO: make it optional
        self.removeStrayPoints = True # TODO: make it optional
        # if last point of a path is further from first point, then an explicit
        # 'lineto' is written to the first point before 'closepath'
        self.closeDist = 0.1
        self.matrices = [[1, 0, 0, 1, 0, 0]]
        self.cssStack = [{}]
        self.gradients = {}
        self.docHeight = 400
        self.docWidth = 400
        self.layerColor = 0
        self.section = None
        self.clipPath = False
        self.epsComments = """%!PS-Adobe-3.0 EPSF-3.0
%%Creator: tzunghaor svg2eps
%%Pages: 1
%%DocumentData: Clean7Bit
%%LanguageLevel: 3
%%DocumentNeededResources: procset Adobe_Illustrator_AI5 1.3 0
%AI5_FileFormat 3
"""
        # TODO: creation date, user etc

        self.epsProlog = """%%BeginProlog
100 dict begin
/tzung_eps_state save def
/dict_count countdictstack def
/op_count count 1 sub def
/Adobe_Illustrator_AI5 where
{ pop } {
    /tzung_strokergb [ 0 0 0 ] def
    /tzung_compound 0 def
    /tzung_closeop { S } def
    /tzung_fillrule 0 def

    /*u { /tzung_compound 1 def newpath /tzung_fillrule 0 def } bind def
    /*U { /tzung_compound 0 def tzung_closeop  } bind def
    /u {} bind def
    /U {} bind def

    /q { clipsave } bind def
    /Q { cliprestore } bind def
    /W { clip } bind def

    /Lb { 10 {pop} repeat } bind def
    /Ln {pop} bind def
    /LB {} bind def


    /w { setlinewidth } bind def
    /J { setlinecap } bind def
    /j { setlinejoin } bind def
    /M { setmiterlimit } bind def
    /d { setdash } bind def

    /m { tzung_compound 0 eq { newpath /tzung_fillrule 0 def } if moveto } bind def
    /l { lineto } bind def
    /c { curveto } bind def

    /XR { /tzung_fillrule exch def } bind def
    /Xa { setrgbcolor } bind def
    /XA { 3 array astore /tzung_strokergb exch def } bind def


    /F { tzung_compound 0 eq {
             tzung_fillrule 0 eq { fill } { eofill } ifelse
         } {
             /tzung_closeop {F} def
         } ifelse } bind def
    /f { closepath F } bind def
    /S { tzung_compound 0 eq {
            tzung_strokergb aload pop setrgbcolor stroke
        } {
             /tzung_closeop {S} def
        } ifelse } bind def
    /s { closepath S } bind def

    /B { tzung_compound 0 eq {
            gsave
            tzung_fillrule 0 eq { fill } { eofill } ifelse
            grestore
            tzung_strokergb aload pop setrgbcolor stroke
         } {
             /tzung_closeop {B} def
        } ifelse } bind def
    /b { closepath B } bind def
    /H { tzung_compound 0 eq {
        }{
            /tzung_closeop {H} def
        } ifelse} bind def
    /h { closepath } bind def
    /N { tzung_compound 0 eq {
        }{
            /tzung_closeop {N} def
        } ifelse} bind def
    /n { closepath N } bind def


    /Bn { /dict_gradients exch dict def} bind def
    /Bd { /tmp_ngradstop exch def /tmp_shadingtype exch def } bind def  %leaves gradient name in stack
    /BD { ]  % this handles only stops that have CMYKRGB color definitions
        % linear gradient stops must be in reverse order, radials in normal order
        aload
        pop
        /tmp_boundaries tmp_ngradstop array def
        /tmp_colors tmp_ngradstop array def
        tmp_shadingtype 0 eq {
            0 1 tmp_ngradstop 1 sub   % for i=0; i<= number of gradient stops - 1; i++
        } {
            tmp_ngradstop 1 sub -1 0   % for i=number of gradient stops - 1; i >= 0; i++
        } ifelse
        {
            /loopvar exch def
            100 div
            tmp_boundaries  loopvar
            3 -1 roll put    %  obj array i => array i obj
            pop % assume gradient middle is always 50
            pop % assume color type is always 2 (CMYKRGB)
            3 array astore
            tmp_colors loopvar
            3 -1 roll put
            pop pop pop pop % drop CMYK values
        } for

        tmp_ngradstop 2 eq {
            /tmp_function 5 dict def
            tmp_boundaries 0 get tmp_boundaries 1 get 2 array astore
            tmp_function /Domain 3 -1 roll put
            tmp_function /FunctionType 2 put
            tmp_function /C0  tmp_colors 0 get put
            tmp_function /C1 tmp_colors 1 get put
            tmp_function /N 1 put

        } {
            /tmp_functions tmp_ngradstop 1 sub array def

            0 1 tmp_ngradstop 2 sub {
                /loopvar exch def
                /tmp_function 5 dict def
                tmp_function /Domain [0 1]  put
                tmp_function /FunctionType 2 put
                tmp_function /C0  tmp_colors loopvar get put
                tmp_function /C1 tmp_colors loopvar 1 add get put
                tmp_function /N 1 put
                tmp_functions loopvar tmp_function put
            } for


            /tmp_function 5 dict def
            tmp_boundaries 0 get tmp_boundaries tmp_ngradstop 1 sub get 2 array astore
            tmp_function /Domain 3 -1 roll  put
            tmp_function /FunctionType 3 put
            tmp_boundaries aload pop
            tmp_ngradstop -1 roll pop pop % remove first and last bounds
            tmp_ngradstop 2 sub array astore
            tmp_function /Bounds 3 -1 roll put
            tmp_function /Functions tmp_functions put

            tmp_ngradstop 1 sub {
                0 1
            } repeat
            tmp_ngradstop 1 sub 2 mul array astore
            tmp_function /Encode 3 -1 roll put

        } ifelse

        /tmp_shading 6 dict def
        tmp_shadingtype 0 eq {
            tmp_shading /ShadingType 2 put
            tmp_shading /Coords [ 0 0 1 0 ] put
        } {
            tmp_shading /ShadingType 3 put
            tmp_shading /Coords [ 0 0 0 0 0 1 ] put
        } ifelse
        tmp_shading /ColorSpace /DeviceRGB put
        tmp_shading /Domain [0 1] put
        tmp_shading /Extend[ true true] put
        tmp_shading /Function tmp_function put

        /tmp_gradient 2 dict def
        tmp_gradient /PatternType 2 put
        tmp_gradient /Shading tmp_shading put

        dict_gradients exch tmp_gradient put % gradient's name is on the top of the stack from Bd operator

    } bind def
    /Lb { 10 { pop } repeat } bind def
    /Ln { pop } bind def
    /Bb { } bind def

    /Bg {
        6 { pop } repeat
        gsave
        4 2 roll
        translate
        exch
        rotate
        dup scale
         exch pop % remove Bg flag
        dict_gradients exch get % now gradient name is on top of the stack
         [ 1 0 0 1 0 0 ]
        makepattern
        /pattern_tmp exch def
        grestore
        pattern_tmp  setpattern
         gsave % save for after pattern fil for possible stroke
    } def
    /BB { grestore 2 eq { s } if } bind def
    /LB { } bind def

} ifelse
"""
        self.epsSetup = """%%BeginSetup
/Adobe_Illustrator_AI5 where
{
    pop
    Adobe_Illustrator_AI5 /initialize get exec
} if
"""
        self.epsLayers = ""
        self.epsTrailer = """%%Trailer
showpage
count op_count sub {pop} repeat
countdictstack dict_count sub {end} repeat
tzung_eps_state restore
end
%%EOF
"""


        self.root = ET.fromstring(self.svg)
        self.walkElem(self.root)
        self.gradientSetup()

        sizeComment = "%%%%BoundingBox: 0 0 %d %d\n" % (math.ceil(self.docWidth), math.ceil(self.docHeight))
        sizeComment += "%%%%HiResBoundingBox: 0 0 %f %f\n" % (self.docWidth, self.docHeight)
        sizeComment += "%%AI5_ArtSize: %f %f\n" % (self.docWidth, self.docHeight)
        pagesetup = """%%%%Page: 1 1
%%%%BeginPageSetup
%%%%PageBoundingBox: 0 0 %d %d
%%%%EndPageSetup
""" % (self.docWidth, self.docHeight)

        eps = self.epsComments + sizeComment + "%%EndComments\n\n"
        eps += self.epsProlog  + "\n%%EndProlog\n\n"
        eps += self.epsSetup + "\n%%EndSetup\n\n"
        eps += pagesetup + self.epsLayers + "\n\n"
        eps += self.epsTrailer

        return eps

import sys

if len(sys.argv) < 2:
    print("missing filename")
    exit(1)

converter = svg2eps(sys.argv[1])

print(converter.convert())
#TODO: show alerts in dialogbox
#converter.showAlerts()
