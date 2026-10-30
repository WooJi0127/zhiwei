/* 收藏 / 本命备份。只处理数据，不访问页面、曲库或 localStorage。 */
(function(root){
  "use strict";

  var FORMAT = "zhiwei-backup";
  var VERSION = 1;
  var MAX_BYTES = 1024 * 1024;
  var MAX_FAVS = 20000;
  var MAX_BIAS = 2000;
  var MAX_ITEM_LENGTH = 512;

  function fail(code, message){
    var error = new Error(message);
    error.code = code;
    throw error;
  }

  /* 按文件的 UTF-8 字节数限制，不把中文和代理对误当作一个字节。 */
  function checkSize(text){
    var bytes = 0;
    for(var i = 0; i < text.length; i++){
      var code = text.charCodeAt(i);
      if(code < 0x80) bytes++;
      else if(code < 0x800) bytes += 2;
      else if(code >= 0xD800 && code <= 0xDBFF &&
              i + 1 < text.length && text.charCodeAt(i + 1) >= 0xDC00 &&
              text.charCodeAt(i + 1) <= 0xDFFF){
        bytes += 4;
        i++;
      } else bytes += 3;
      if(bytes > MAX_BYTES) fail("TOO_LARGE", "备份文件不能超过 1 MB。");
    }
  }

  function unique(list){
    var seen = Object.create(null);
    return list.filter(function(value){
      if(seen[value]) return false;
      seen[value] = true;
      return true;
    });
  }

  function selectionList(list, label, maxItems){
    if(!Array.isArray(list)) fail("INVALID_LIST", label + "必须是列表。");
    if(list.length > maxItems) fail("TOO_MANY_ITEMS", label + "条目过多，无法导入。");
    for(var i = 0; i < list.length; i++){
      if(typeof list[i] !== "string" || !list[i].trim() ||
         list[i].length > MAX_ITEM_LENGTH || /[\u0000-\u001F\u007F]/.test(list[i])){
        fail("INVALID_ITEM", label + "中含有无效条目，原有内容未改变。");
      }
    }
    /* 不改写 ID 或艺人名；即使历史年份尚未加载，也保留原值。 */
    return unique(list);
  }

  function validate(value){
    if(!value || typeof value !== "object" || Array.isArray(value) || value.format !== FORMAT){
      fail("INVALID_FORMAT", "这不是知未的收藏备份文件。");
    }
    if(value.version !== VERSION){
      fail("INVALID_VERSION", "暂不支持这个备份版本，请使用当前版本导出的文件。");
    }
    var result = {
      format:FORMAT,
      version:VERSION,
      favs:selectionList(value.favs, "收藏", MAX_FAVS),
      bias:selectionList(value.bias, "本命", MAX_BIAS)
    };
    if(typeof value.exportedAt === "string" && value.exportedAt.length <= 64){
      result.exportedAt = value.exportedAt;
    }
    return result;
  }

  function create(favs, bias){
    var result = validate({format:FORMAT, version:VERSION, favs:favs, bias:bias});
    result.exportedAt = new Date().toISOString();
    /* 界面以两个空格缩进下载；导出的文件也必须可再次导入。 */
    checkSize(JSON.stringify(result, null, 2));
    return result;
  }

  function parse(text){
    if(typeof text !== "string") fail("INVALID_JSON", "请选择 JSON 格式的备份文件。");
    checkSize(text);
    var value;
    try{
      value = JSON.parse(text.replace(/^\uFEFF/, ""));
    }catch(error){
      fail("INVALID_JSON", "文件不是有效的 JSON，原有内容未改变。");
    }
    return validate(value);
  }

  function merge(favs, bias, incoming){
    var checked = validate(incoming);
    var currentFavs = selectionList(favs, "收藏", MAX_FAVS);
    var currentBias = selectionList(bias, "本命", MAX_BIAS);
    var result = create(unique(currentFavs.concat(checked.favs)), unique(currentBias.concat(checked.bias)));
    return {
      favs:result.favs,
      bias:result.bias,
      addedFavs:result.favs.length - currentFavs.length,
      addedBias:result.bias.length - currentBias.length
    };
  }

  root.ZWBackup = {create:create, parse:parse, merge:merge, MAX_BYTES:MAX_BYTES};
})(window);
