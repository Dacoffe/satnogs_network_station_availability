// This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define(['kaitai-struct/KaitaiStream'], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('kaitai-struct/KaitaiStream'));
  } else {
    root.Ax25monitor = factory(root.KaitaiStream);
  }
}(this, function (KaitaiStream) {
/**
 * :field dest_callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
 * :field src_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
 * :field src_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
 * :field dest_ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
 * :field rpt_callsign: ax25_frame.ax25_header.repeater.rpt_instance[0].rpt_callsign_raw.callsign_ror.callsign
 * :field ctl: ax25_frame.ax25_header.ctl
 * :field pid: ax25_frame.payload.pid
 * :field monitor: ax25_frame.payload.ax25_info.data_monitor
 *
 * Attention: `rpt_callsign` cannot be accessed because `rpt_instance` is an
 * array of unknown size at the beginning of the parsing process! Left an
 * example in here.
 */

var Ax25monitor = (function() {
  function Ax25monitor(_io, _parent, _root) {
    this._io = _io;
    this._parent = _parent;
    this._root = _root || this;

    this._read();
  }
  Ax25monitor.prototype._read = function() {
    this.ax25Frame = new Ax25Frame(this._io, this, this._root);
  }

  var Ax25Frame = Ax25monitor.Ax25Frame = (function() {
    function Ax25Frame(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    Ax25Frame.prototype._read = function() {
      this.ax25Header = new Ax25Header(this._io, this, this._root);
      switch ((this.ax25Header.ctl & 19)) {
      case 0:
        this.payload = new IFrame(this._io, this, this._root);
        break;
      case 3:
        this.payload = new UiFrame(this._io, this, this._root);
        break;
      case 19:
        this.payload = new UiFrame(this._io, this, this._root);
        break;
      case 16:
        this.payload = new IFrame(this._io, this, this._root);
        break;
      case 18:
        this.payload = new IFrame(this._io, this, this._root);
        break;
      case 2:
        this.payload = new IFrame(this._io, this, this._root);
        break;
      }
    }

    return Ax25Frame;
  })();

  var Ax25Header = Ax25monitor.Ax25Header = (function() {
    function Ax25Header(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    Ax25Header.prototype._read = function() {
      this.destCallsignRaw = new CallsignRaw(this._io, this, this._root);
      this.destSsidRaw = new SsidMask(this._io, this, this._root);
      this.srcCallsignRaw = new CallsignRaw(this._io, this, this._root);
      this.srcSsidRaw = new SsidMask(this._io, this, this._root);
      if ((this.srcSsidRaw.ssidMask & 1) == 0) {
        this.repeater = new Repeater(this._io, this, this._root);
      }
      this.ctl = this._io.readU1();
    }

    /**
     * Repeater flag is set!
     */

    return Ax25Header;
  })();

  var UiFrame = Ax25monitor.UiFrame = (function() {
    function UiFrame(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    UiFrame.prototype._read = function() {
      this.pid = this._io.readU1();
      this._raw_ax25Info = this._io.readBytesFull();
      var _io__raw_ax25Info = new KaitaiStream(this._raw_ax25Info);
      this.ax25Info = new Ax25InfoData(_io__raw_ax25Info, this, this._root);
    }

    return UiFrame;
  })();

  var Callsign = Ax25monitor.Callsign = (function() {
    function Callsign(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    Callsign.prototype._read = function() {
      this.callsign = KaitaiStream.bytesToStr(this._io.readBytes(6), "ASCII");
    }

    return Callsign;
  })();

  var IFrame = Ax25monitor.IFrame = (function() {
    function IFrame(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    IFrame.prototype._read = function() {
      this.pid = this._io.readU1();
      this._raw_ax25Info = this._io.readBytesFull();
      var _io__raw_ax25Info = new KaitaiStream(this._raw_ax25Info);
      this.ax25Info = new Ax25InfoData(_io__raw_ax25Info, this, this._root);
    }

    return IFrame;
  })();

  var SsidMask = Ax25monitor.SsidMask = (function() {
    function SsidMask(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    SsidMask.prototype._read = function() {
      this.ssidMask = this._io.readU1();
    }
    Object.defineProperty(SsidMask.prototype, 'ssid', {
      get: function() {
        if (this._m_ssid !== undefined)
          return this._m_ssid;
        this._m_ssid = ((this.ssidMask & 15) >>> 1);
        return this._m_ssid;
      }
    });

    return SsidMask;
  })();

  var Repeaters = Ax25monitor.Repeaters = (function() {
    function Repeaters(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    Repeaters.prototype._read = function() {
      this.rptCallsignRaw = new CallsignRaw(this._io, this, this._root);
      this.rptSsidRaw = new SsidMask(this._io, this, this._root);
    }

    return Repeaters;
  })();

  var Repeater = Ax25monitor.Repeater = (function() {
    function Repeater(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    Repeater.prototype._read = function() {
      this.rptInstance = []
      var i = 0;
      do {
        var _ = new Repeaters(this._io, this, this._root);
        this.rptInstance.push(_);
        i++;
      } while (!((_.rptSsidRaw.ssidMask & 1) == 1));
    }

    /**
     * Repeat until no repeater flag is set!
     */

    return Repeater;
  })();

  var CallsignRaw = Ax25monitor.CallsignRaw = (function() {
    function CallsignRaw(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    CallsignRaw.prototype._read = function() {
      this._raw__raw_callsignRor = this._io.readBytes(6);
      this._raw_callsignRor = KaitaiStream.processRotateLeft(this._raw__raw_callsignRor, 8 - (1), 1);
      var _io__raw_callsignRor = new KaitaiStream(this._raw_callsignRor);
      this.callsignRor = new Callsign(_io__raw_callsignRor, this, this._root);
    }

    return CallsignRaw;
  })();

  var Ax25InfoData = Ax25monitor.Ax25InfoData = (function() {
    function Ax25InfoData(_io, _parent, _root) {
      this._io = _io;
      this._parent = _parent;
      this._root = _root || this;

      this._read();
    }
    Ax25InfoData.prototype._read = function() {
      this.dataMonitor = KaitaiStream.bytesToStr(this._io.readBytesFull(), "utf-8");
    }

    return Ax25InfoData;
  })();

  /**
   * @see {@link https://www.tapr.org/pub_ax25.html|Source}
   */

  return Ax25monitor;
})();
return Ax25monitor;
}));
