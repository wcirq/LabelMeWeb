import os.path as osp
import shutil

import yaml

from labelme.logger import logger


here = osp.dirname(osp.abspath(__file__))


def update_dict(target_dict, new_dict, validate_item=None):
    for key, value in new_dict.items():
        if validate_item:
            validate_item(key, value)
        if key not in target_dict:
            logger.warn('Skipping unexpected key in config: {}'
                        .format(key))
            continue
        if isinstance(target_dict[key], dict) and \
                isinstance(value, dict):
            update_dict(target_dict[key], value, validate_item=validate_item)
        else:
            target_dict[key] = value


# -----------------------------------------------------------------------------


def get_default_config():
    config_file = osp.join(here, 'default_config.yaml')
    try:
        with open(config_file) as f:
            config = yaml.load(f)
    except:
        config = {'auto_save': False, 'display_label_popup': True, 'store_data': False, 'keep_prev': False,
                        'logger_level': 'info', 'flags': None, 'labels': 'labelme/config/labels.txt', 'aa': None,
                        'file_search': None, 'sort_labels': True, 'validate_label': None,
                        'flag_dock': {'show': True, 'closable': True, 'movable': True, 'floatable': True},
                        'label_dock': {'show': True, 'closable': True, 'movable': True, 'floatable': True},
                        'shape_dock': {'show': True, 'closable': True, 'movable': True, 'floatable': True},
                        'file_dock': {'show': True, 'closable': True, 'movable': True, 'floatable': True},
                        'show_label_text_field': True, 'label_completion': 'startswith',
                        'fit_to_content': {'column': True, 'row': False}, 'epsilon': 20.0,
                        'shortcuts': {'close': 'Ctrl+W', 'open': 'Ctrl+O', 'open_dir': 'Ctrl+U', 'quit': 'Ctrl+Q',
                                      'save': 'Ctrl+S', 'save_as': 'Ctrl+Shift+S', 'save_to': None,
                                      'delete_file': 'Ctrl+Delete', 'ignoreImage': None,
                                      'open_next': ['D', 'Ctrl+Shift+D'], 'open_prev': ['A', 'Ctrl+Shift+A'],
                                      'zoom_in': ['Ctrl++', 'Ctrl+='], 'zoom_out': 'Ctrl+-',
                                      'zoom_to_original': 'Ctrl+0', 'fit_window': 'Ctrl+F', 'fit_width': 'Ctrl+Shift+F',
                                      'add_point': 'Ctrl+Shift+P', 'create_polygon': 'Ctrl+N',
                                      'create_rectangle': 'Ctrl+R', 'create_circle': 'Ctrl+Q', 'create_line': None,
                                      'create_point': None, 'create_linestrip': None, 'edit_polygon': 'Ctrl+J',
                                      'delete_polygon': 'Delete', 'duplicate_polygon': 'Ctrl+D', 'undo': 'Ctrl+Z',
                                      'undo_last_point': ['Ctrl+Z', 'Backspace'], 'edit_label': 'Ctrl+E',
                                      'edit_line_color': 'Ctrl+L', 'edit_fill_color': 'Ctrl+Shift+L',
                                      'toggle_keep_prev_mode': 'Ctrl+P'}}

    # save default config to ~/.labelmerc
    user_config_file = osp.join(osp.expanduser('~'), '.labelmerc')
    if not osp.exists(user_config_file):
        try:
            shutil.copy(config_file, user_config_file)
        except Exception:
            logger.warn('Failed to save config: {}'.format(user_config_file))

    return config


def validate_config_item(key, value):
    if key == 'validate_label' and value not in [None, 'exact', 'instance']:
        raise ValueError(
            "Unexpected value for config key 'validate_label': {}"
            .format(value)
        )
    if key == 'labels' and value is not None and len(value) != len(set(value)):
        raise ValueError(
            "Duplicates are detected for config key 'labels': {}".format(value)
        )


def get_config(config_from_args=None, config_file=None):
    # Configuration load order:
    #
    #   1. default config (lowest priority)
    #   2. config file passed by command line argument or ~/.labelmerc
    #   3. command line argument (highest priority)

    # 1. default config
    config = get_default_config()

    # 2. config from yaml file
    if config_file is not None and osp.exists(config_file):
        with open(config_file) as f:
            user_config = yaml.load(f) or {}
        update_dict(config, user_config, validate_item=validate_config_item)

    # 3. command line argument
    if config_from_args is not None:
        update_dict(config, config_from_args,
                    validate_item=validate_config_item)

    return config
